"""One-use receipt for a model run fused with the same-frame PL transform."""

class NativeForward:
    def __init__(self, owner, role, token, reply, directory, image_bgr=None):
        self.owner=owner;self.role=role;self.token=token;self.reply=reply
        self.directory=directory;self.image_bgr=image_bgr;self.consumed=False

    def claim(self, owner, role, frame):
        if (self.consumed or owner is not self.owner or role!=self.role
                or self.reply.get('forward_token')!=self.token or frame is None
                or self.reply.get('frame_id')!=frame['frame_id']
                or self.reply.get('frame_token')!=frame['frame_token']):
            raise RuntimeError('Native model receipt is consumed or belongs to another input')
        self.consumed=True
        return self.reply
