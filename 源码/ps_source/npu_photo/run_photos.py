"""PS image preparation/postprocessing around actual ZG330 network inference."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import select
import shutil
import subprocess
import time
import cv2
import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class Runner:
    def __init__(self, root, out):
        self.root, self.out, self.buffer = root, out, b""
        self.log = (out / "runner-stderr.log").open("wb")
        self.stdout_log = (out / 'runner-stdout.log').open('wb')
        self.process = None
        try:
            self.start_process()
        except BaseException:
            self.close()
            raise

    def start_process(self):
        self.buffer = b""
        root = self.root
        self.process = subprocess.Popen([str(root / "wcis_face_npu"), "--run", str(root / "models.json")],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log)
        try:
            self.ready = self.read()
            if self.ready["status"] != "ready":
                raise RuntimeError("NPU runner did not initialize")
        except BaseException:
            self.close()
            raise

    def read(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                marker = line.find(b"WCIS_RESULT ")
                if marker >= 0:
                    # The SDK may leave an ANSI progress erase before our JSON.
                    value = json.loads(line[marker+len(b"WCIS_RESULT "):])
                    if value["status"] == "error":
                        raise RuntimeError(value["message"])
                    return value
                continue
            if select.select([self.process.stdout], [], [], max(0, deadline - time.monotonic()))[0]:
                data = os.read(self.process.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError("NPU runner exited before returning a result")
                self.stdout_log.write(data)
                self.stdout_log.flush()
                self.buffer += data
        raise TimeoutError("NPU request exceeded 30 seconds; review hardware before retry")

    def forward(self, role, data, stem):
        if self.process is None:
            self.start_process()
        path = self.out / "tensors" / (stem + "-" + role + ".f32")
        path.parent.mkdir(exist_ok=True)
        np.asarray(data, dtype=np.float32).tofile(str(path))
        directory = self.out / "raw" / stem / role
        request = {"role": role, "input_f32": str(path), "output_directory": str(directory)}
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        self.process.stdin.flush()
        result = self.read()
        if result["status"] != "forwarded" or result["npu_bound_ops"] < 1:
            raise RuntimeError("No ZG330 execution evidence")
        # The second model fails in a shared device process on this SDK/board.
        # Use a fresh process for each request, without a CPU inference fallback.
        self.finish_process()
        result['session_lifecycle'] = 'isolated_process_per_request'
        save(self.out / "timing" / (stem + "-" + role + ".json"), result)
        values = []
        for record in result["outputs"]:
            array = np.fromfile(record["file"], dtype=np.float32)
            if len(array) != record["elements"] or not np.all(np.isfinite(array)):
                raise RuntimeError("Corrupt NPU output")
            values.append(array)
        return values, result

    def finish_process(self, require_success=True):
        if self.process is not None and self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.process is not None:
            code = self.process.returncode
            self.process.stdout.close()
            self.process = None
            if code and require_success:
                raise RuntimeError('NPU worker did not exit cleanly: '+str(code))

    def close(self):
        try:
            self.finish_process(require_success=False)
        finally:
            self.log.close()
            self.stdout_log.close()


def prepare(image):
    h, w = image.shape[:2]
    ratio = min(640 / w, 640 / h)
    dw, dh = max(1, int(w * ratio)), max(1, int(h * ratio))
    padded = np.zeros((640, 640, 3), dtype=np.uint8)
    padded[:dh, :dw] = cv2.resize(image, (dw, dh), interpolation=cv2.INTER_LINEAR)
    return padded, dw / w, dh / h


def decode(values, sx, sy, logits=False):
    if len(values) != 12:
        raise ValueError("YuNet requires 12 outputs")
    candidates = []
    for level, stride in enumerate((8, 16, 32)):
        side, count = 640 // stride, (640 // stride) ** 2
        cls, obj, boxes, kps = values[level], values[level + 3], values[level + 6], values[level + 9]
        if logits:
            cls = 1.0 / (1.0 + np.exp(-np.clip(cls, -80, 80)))
            obj = 1.0 / (1.0 + np.exp(-np.clip(obj, -80, 80)))
        if (len(cls), len(obj), len(boxes), len(kps)) != (count, count, count * 4, count * 10):
            raise ValueError("Unexpected YuNet output order/shape")
        boxes, kps = boxes.reshape(count, 4), kps.reshape(count, 5, 2)
        scores = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
        for idx in np.flatnonzero(scores >= 0.6):
            x, y = int(idx) % side, int(idx) // side
            cx, cy = (x + boxes[idx, 0]) * stride, (y + boxes[idx, 1]) * stride
            w, h = np.exp(boxes[idx, 2]) * stride, np.exp(boxes[idx, 3]) * stride
            points = (kps[idx] + np.array([x, y], dtype=np.float32)) * stride
            box = [float(cx - w / 2), float(cy - h / 2), float(cx + w / 2), float(cy + h / 2)]
            if not np.all(np.isfinite(box)) or max(w, h) > 100000:
                raise ValueError("Invalid decoded geometry")
            candidates.append({"box": box, "score": float(scores[idx]), "landmarks": points.tolist()})
    rectangles = [[int(d['box'][0]), int(d['box'][1]), int(d['box'][2]-d['box'][0]), int(d['box'][3]-d['box'][1])] for d in candidates]
    indices = cv2.dnn.NMSBoxes(rectangles, [d['score'] for d in candidates], 0.6, 0.3, eta=1.0, top_k=5000) if candidates else []
    kept = [candidates[int(i)] for i in np.asarray(indices).flatten()]
    for d in kept:
        d["box"] = (np.array(d["box"]) / [sx, sy, sx, sy]).tolist()
        d["landmarks"] = (np.array(d["landmarks"]) / [sx, sy]).tolist()
    return kept


def alignment_matrix(face):
    """Existing least-squares similarity fit, exposed for the PL descriptor.

    Same five-point ArcFace geometry as the verified InsightFace reference;
    this refactor preserves the deployed arithmetic and pixel baseline.
    """
    source = np.array(face["landmarks"], dtype=np.float64)
    if source.shape != (5, 2) or not np.all(np.isfinite(source)):
        raise ValueError("Expected five finite landmarks in original-frame coordinates")
    target = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32).astype(np.float64)
    sm, tm = source.mean(axis=0), target.mean(axis=0)
    s, t = source - sm, target - tm
    denom = float(np.sum(s * s))
    if denom < 1e-10:
        raise ValueError("Degenerate landmarks")
    a = float(np.sum(s * t)) / denom
    b = float(np.sum(s[:, 0] * t[:, 1] - s[:, 1] * t[:, 0])) / denom
    matrix = np.array([[a, -b, tm[0] - a * sm[0] + b * sm[1]], [b, a, tm[1] - b * sm[0] - a * sm[1]]])
    return matrix


def align(image, face):
    return cv2.warpAffine(image, alignment_matrix(face), (112, 112), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    config = json.loads((root / "models.json").read_text())
    for role, record in config["models"].items():
        for key in ("json", "raw"):
            if sha(root / record[key]) != record[key + "_sha256"]:
                raise ValueError("Model checksum mismatch: " + role)
    sources = json.loads((root / "samples/sources.json").read_text())
    for r in sources["files"]:
        if sha(root / "samples" / r["file"]) != r["sha256"]:
            raise ValueError("Photo checksum mismatch")
    if not args.run:
        print("Files verified; pass --run after checking exclusive NPU ownership.")
        return
    out.mkdir(parents=True, exist_ok=True)
    lock = (root / "npu.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    review = root.parents[1] / 'hardware-review-required.json'
    if review.exists() and json.loads(review.read_text()).get('boot_id') == boot_id:
        raise RuntimeError('Previous NPU failure in this boot; review hardware before another run')
    try:
        runner = Runner(root, out)
    except BaseException as error:
        save(review, {'boot_id':boot_id,'error_type':type(error).__name__,'message':str(error),'automatic_retry':False})
        raise
    pipeline = "yunet-mf-" + config['precision'] + "-npu:" + hashlib.sha256((root / "models.json").read_bytes()).hexdigest()
    entries, features, checks = [], {}, []
    start = datetime.now(timezone.utc).isoformat()
    site = out / "site"
    assets = site / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    try:
        def analyze(record):
            name = record["file"]
            image = cv2.imread(str(root / "samples" / name), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
            if image is None:
                raise ValueError("Cannot decode photo")
            padded, sx, sy = prepare(image)
            values, dt = runner.forward("yunet", padded.astype(np.float32), Path(name).stem)
            faces = decode(values, sx, sy, logits=config.get('detector_activation') == 'host_sigmoid')
            if len(faces) != 1:
                return {"faces": faces, "face_count": len(faces), "status": "no_face" if not faces else "multiple_faces"}
            crop = align(image, faces[0])
            tensor = (crop[:, :, ::-1].astype(np.float32) - np.float32(127.5)) / np.float32(127.5)
            raw, rt = runner.forward("mobilefacenet", tensor, Path(name).stem)
            if len(raw) != 1 or len(raw[0]) != 512:
                raise ValueError("Expected 512 features")
            norm = float(np.linalg.norm(raw[0].astype(np.float64)))
            if norm < 1e-10:
                raise ValueError("Zero feature vector")
            cv2.imwrite(str(assets / (Path(name).stem + "-aligned.png")), crop)
            return {"status": "extracted", "face": faces[0], "embedding": (raw[0].astype(np.float64) / norm).tolist(),
                    "backend": "zg330_npu_and_host", "pipeline_id": pipeline, "timing": {"detector": dt["elapsed_ms"], "recognizer": rt["elapsed_ms"]}}

        records = sources["files"]
        for record in records:
            print("NPU extract", record["file"], flush=True)
            feature = analyze(record)
            if feature["status"] != "extracted":
                raise ValueError("Public functional fixture did not have one face: " + record["file"])
            features[record["file"]] = feature
            save(out / "features" / (record["file"] + ".json"), feature)
            reference_path = root / "cpu-features" / (record["file"] + ".json")
            if reference_path.exists():
                reference = json.loads(reference_path.read_text())
                reference_embedding = np.array(reference["embedding"], dtype=np.float64)
                actual_embedding = np.array(feature["embedding"], dtype=np.float64)
                score = float(np.dot(reference_embedding, actual_embedding) / (np.linalg.norm(reference_embedding) * np.linalg.norm(actual_embedding)))
                boxes_delta = float(np.max(np.abs(np.array(reference["face"]["box"]) - np.array(feature["face"]["box"]))))
                checks.append({"file": record["file"], "kind": "cpu_npu_reference", "feature_cosine": score,
                               "box_delta_px": boxes_delta, "criterion": "full-pipeline feature cosine >= 0.99 (engineering check)", "passed": score >= 0.99})
            shutil.copyfile(root / "samples" / record["file"], assets / record["file"])
        templates = {r["expected"]: np.array(features[r["file"]]["embedding"]) for r in records if r["role"] == "enroll"}
        pairs = []
        for record in records:
            if record["role"] == "calibration":
                for identity, template in templates.items():
                    pairs.append({"file": record["file"], "template": identity, "same": identity == record["expected"],
                                  "cosine": float(np.dot(features[record["file"]]["embedding"], template))})
        genuine = [p["cosine"] for p in pairs if p["same"]]
        impostor = [p["cosine"] for p in pairs if not p["same"]]
        if min(genuine) <= max(impostor):
            raise ValueError("NPU calibration has no separating gap")
        threshold = (min(genuine) + max(impostor)) / 2
        save(out / "identities.json", {"pipeline_id": pipeline, "people": {k: v.tolist() for k, v in templates.items()}})
        for record in records:
            name = record["file"]
            feature = features[name]
            entry = dict(record, image="assets/" + name, aligned="assets/" + Path(name).stem + "-aligned.png", face=feature["face"], backend=feature["backend"], pipeline_id=pipeline, result=None)
            if record["role"] == "test":
                scores = {identity: float(np.dot(feature["embedding"], template)) for identity, template in templates.items()}
                sorted_scores = sorted(scores.items(), key=lambda p: p[1], reverse=True)
                candidate, score = sorted_scores[0]
                accepted = score >= threshold and abs(score - sorted_scores[1][1]) > 1e-6
                result = {"name": candidate if accepted else "未知", "status": "recognized" if accepted else "unknown",
                          "similarity": score, "threshold": threshold, "scores": scores, "backend": feature["backend"], "pipeline_id": pipeline}
                entry["result"], entry["passed"] = result, result["name"] == record["expected"]
                checks.append({"file": name, "expected": record["expected"], "actual": result["name"], "passed": entry["passed"]})
                save(out / "results" / (name + ".json"), result)
            entries.append(entry)
        for name, status in (("no-face.png", "no_face"), ("two-faces.png", "multiple_faces")):
            result = analyze({"file": name})
            passed = result["status"] == status
            checks.append({"file": name, "expected": status, "actual": result["status"], "passed": passed})
            shutil.copyfile(root / "samples" / name, assets / name)
            entries.append({"file": name, "role": "failure", "expected": status, "image": "assets/" + name,
                            "sha256": sha(root / "samples" / name), "backend": "zg330_npu_and_host", "result": result,
                            "faces": result["faces"], "passed": passed, "url": None, "synthetic": True})
        report = {"schema_version": 1, "run_utc": start, "backend": "zg330_npu_and_host", "pipeline_id": pipeline,
                  "scope": "Board file input; PS preprocessing and decoding; real NPU networks; no camera or new PL firmware",
                  "public_photos": len(records), "held_out_recognition": 7, "failure_cases": 2, "threshold": threshold,
                  "all_passed": all(c["passed"] for c in checks), "checks": checks, "contracts": runner.ready["contracts"],
                  "opencv_version": cv2.__version__, "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
        save(out / "verification.json", report)
        save(site / "results.json", {"report": report, "entries": entries})
        print(json.dumps(report, ensure_ascii=False), flush=True)
        if not report["all_passed"]:
            raise SystemExit(1)
    except BaseException as error:
        save(out / "failure.json", {"error_type": type(error).__name__, "message": str(error), "automatic_retry": False})
        if not isinstance(error, SystemExit):
            save(review, {'boot_id':boot_id,'error_type':type(error).__name__,'message':str(error),'automatic_retry':False})
        raise
    finally:
        runner.close()


if __name__ == "__main__":
    main()
