"""Persistent, atomic enrollment store; deleted entries stop matching immediately."""
import fcntl,json,uuid
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import cv2
import numpy as np
from run_photos import save,sha

class Gallery:
    def __init__(self,root):
        self.root=Path(root)
        config=json.loads((self.root/'models.json').read_text())
        self.pipeline='yunet-mf-'+config['precision']+'-npu:'+sha(self.root/'models.json')
        self.base=self.root.parents[1]/'galleries'/sha(self.root/'models.json')[:16]
        self.base.mkdir(parents=True,exist_ok=True)
        (self.base/'photos').mkdir(exist_ok=True)
        (self.base/'trash').mkdir(exist_ok=True)
        self.path=self.base/'gallery.json'
        with self.locked() as db:
            if db is None:
                db={'schema_version':1,'pipeline_id':self.pipeline,'revision':0,'people':[]}
                evidence=json.loads((self.root/'run-01/verification.json').read_text())
                if not evidence['all_passed'] or evidence['pipeline_id']!=self.pipeline:
                    raise RuntimeError('Cannot seed an unvalidated model gallery')
                sources=json.loads((self.root/'samples/sources.json').read_text())
                for record in sources['files']:
                    if record['role']!='enroll':continue
                    feature=json.loads((self.root/'run-01/features'/(record['file']+'.json')).read_text())
                    photo_id=uuid.uuid4().hex
                    cv2.imwrite(str(self.base/'photos'/(photo_id+'.png')),cv2.imread(str(self.root/'samples'/record['file'])))
                    db['people'].append({'id':uuid.uuid4().hex,'name':record['expected'],'photos':[
                        {'id':photo_id,'sha256':record['sha256'],'file':record['file'],'embedding':feature['embedding'],'created':self.now()}]})
                save(self.path,db)

    @staticmethod
    def now():return datetime.now(timezone.utc).isoformat()

    @contextmanager
    def locked(self):
        with (self.base/'gallery.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            db=json.loads(self.path.read_text()) if self.path.exists() else None
            if db and db['pipeline_id']!=self.pipeline:raise RuntimeError('Gallery/model version mismatch')
            yield db

    def templates(self):
        with self.locked() as db:
            return self.templates_from_db(db)

    def templates_from_db(self,db):
        templates={}
        for person in db['people']:
            vectors=np.asarray([p['embedding'] for p in person['photos']],np.float64)
            if vectors.ndim!=2 or vectors.shape[1]!=512 or not np.all(np.isfinite(vectors)):
                raise RuntimeError('Invalid enrollment feature data')
            center=vectors.mean(axis=0);norm=float(np.linalg.norm(center))
            if norm<1e-10:raise RuntimeError('Enrollment features cancel; replace conflicting photos')
            templates[person['name']]=(center/norm).tolist()
        return {'pipeline_id':self.pipeline,'people':templates}

    def public(self):
        with self.locked() as db:
            return {'revision':db['revision'],'people':[{'id':p['id'],'name':p['name'],'count':len(p['photos']),
                'photos':[{'id':v['id'],'file':v['file'],'created':v['created'],'image':'/gallery-media/'+v['id']} for v in p['photos']]} for p in db['people']]}

    def check_new(self,name,digest):
        name=name.strip()
        if not name or len(name)>40 or any(ord(c)<32 for c in name):raise ValueError('姓名需为 1～40 个可显示字符')
        with self.locked() as db:
            for person in db['people']:
                if any(p['sha256']==digest for p in person['photos']):raise ValueError('这张照片已经登记，请使用另一张照片')
                if person['name']==name and len(person['photos'])>=30:raise ValueError('每个人最多登记 30 张照片')
            if len(db['people'])>=100 and not any(p['name']==name for p in db['people']):raise ValueError('登记人数已达到 100 人')
        return name

    def add(self,name,photo,embedding,filename):
        digest=sha(photo);name=self.check_new(name,digest)
        vector=np.asarray(embedding,np.float64)
        if vector.shape!=(512,) or not np.all(np.isfinite(vector)) or abs(np.linalg.norm(vector)-1)>1e-6:
            raise ValueError('登记特征无效')
        photo_id=uuid.uuid4().hex
        image=cv2.imread(str(photo),cv2.IMREAD_COLOR|cv2.IMREAD_IGNORE_ORIENTATION)
        if image is None or not cv2.imwrite(str(self.base/'photos'/(photo_id+'.png')),image):raise ValueError('无法保存登记照片')
        with self.locked() as db:
            person=next((p for p in db['people'] if p['name']==name),None)
            if person is None:
                person={'id':uuid.uuid4().hex,'name':name,'photos':[]};db['people'].append(person)
            person['photos'].append({'id':photo_id,'file':filename,'sha256':digest,'embedding':vector.tolist(),'created':self.now()})
            db['revision']+=1;save(self.path,db)
        return self.public()

    def photo_path(self,photo_id):
        with self.locked() as db:
            if any(p['id']==photo_id for person in db['people'] for p in person['photos']):
                return self.base/'photos'/(photo_id+'.png')
        raise KeyError('登记照片不存在')

    def delete(self,person_id,photo_id=None):
        with self.locked() as db:
            person=next((p for p in db['people'] if p['id']==person_id),None)
            if person is None:raise KeyError('人员不存在')
            removed=[p for p in person['photos'] if photo_id is None or p['id']==photo_id]
            if not removed:raise KeyError('登记照片不存在')
            trash=self.base/'trash'/uuid.uuid4().hex;trash.mkdir()
            save(trash/'removed.json',{'pipeline_id':self.pipeline,'person_id':person['id'],'name':person['name'],
                                      'photos':removed,'deleted':self.now()})
            person['photos']=[p for p in person['photos'] if p not in removed]
            if not person['photos']:db['people'].remove(person)
            db['revision']+=1;save(self.path,db)
            for p in removed:
                source=self.base/'photos'/(p['id']+'.png')
                if source.exists():source.rename(trash/source.name)
        return self.public()
