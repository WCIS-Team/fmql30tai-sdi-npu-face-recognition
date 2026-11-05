# Silent-Face-Anti-Spoofing reference

Upstream: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing

Revision: `b6d5f04ad78778917853b25c778acef6d5626d15`.

The crop geometry in `../face_pad.py` is adapted from `src/generate_patches.py`
(author Zhu Ying, MiniVision); validation, crop-local RTL descriptor generation
and backend evidence handling are project additions. The full upstream Apache
2.0 license is retained beside this notice. Other upstream source and model
weights are downloaded only to isolated task directories, with SHA-256 records
in `../../scripts/face_pad_reference.json`. Upstream sample files are demonstration
inputs, not this project's security validation dataset.
