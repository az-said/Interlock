"""
Google Cloud Storage JSON API over urllib. Standard library only, like the rest of the repo.

The token is read at runtime: GCS_TOKEN from the environment, else `gcloud auth print-access-token`.
It is never written anywhere.

Every agent write in this scenario goes through write(), so all three systems crash at the same
two points, with a real SIGKILL of the worker process (never an exception):

    INTERLOCK_CRASH=before_send    the process dies right before the upload request leaves
    INTERLOCK_CRASH=after_commit   GCS answered 200 and the body was parsed, then the process dies

The crash is one-shot: it writes crashed_at to INTERLOCK_CASE_DIR, then kills itself.
"""
import base64, hashlib, json, os, signal, subprocess, time, urllib.error, urllib.parse, urllib.request

API = "https://storage.googleapis.com/storage/v1"
UPLOAD = "https://storage.googleapis.com/upload/storage/v1"
PREFIX = "interlock-sandbox"        # the only resources this scenario may touch


class GcsError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"GCS {code}: {message}")
        self.code = code


def token():
    return os.environ.get("GCS_TOKEN") or subprocess.run(
        ["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()


def md5_b64(body):
    return base64.b64encode(hashlib.md5(body.encode()).digest()).decode()


def _q(name):
    return urllib.parse.quote(name, safe="")


class Gcs:
    def __init__(self, bearer=None, timeout=10):
        self._auth = "Bearer " + (bearer or token())
        self.timeout = timeout      # well inside the gate's claim_ttl

    def request(self, method, url, body=None, content_type="application/json"):
        if "/b/" + PREFIX not in url and not url.startswith(API + "/b?"):
            raise ValueError(f"refusing to touch a resource outside {PREFIX}*: {url}")
        for attempt in range(5):
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header("Authorization", self._auth)
            if body is not None:
                req.add_header("Content-Type", content_type)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                # 429/503 mean the request was not applied (GCS allows about one write per second per object)
                if e.code in (429, 503) and attempt < 4:
                    time.sleep(1 + attempt)
                    continue
                message = json.loads(e.read() or b"{}").get("error", {}).get("message")
                raise GcsError(e.code, message) from None

    # buckets
    def create_bucket(self, project, name):
        return self.request("POST", f"{API}/b?project={project}", json.dumps({
            "name": name, "location": "US", "versioning": {"enabled": True},
            "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}}}).encode())

    def delete_bucket(self, bucket):
        for v in self.versions(bucket, ""):
            self.request("DELETE", f"{API}/b/{bucket}/o/{_q(v['name'])}?generation={v['generation']}")
        self.request("DELETE", f"{API}/b/{bucket}")

    # objects
    def upload(self, bucket, name, body, metadata, if_generation_match=None):
        """Multipart upload: content plus custom metadata in one request. Returns the object resource."""
        boundary = "interlock" + os.urandom(8).hex()
        meta = json.dumps({"name": name, "contentType": "application/json", "metadata": metadata})
        payload = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
                   f"--{boundary}\r\nContent-Type: application/json\r\n\r\n{body}\r\n--{boundary}--").encode()
        url = f"{UPLOAD}/b/{bucket}/o?uploadType=multipart&name={_q(name)}"
        if if_generation_match is not None:
            url += f"&ifGenerationMatch={if_generation_match}"
        return self.request("POST", url, payload, f"multipart/related; boundary={boundary}")

    def get(self, bucket, name):
        """The live object's resource (generation, md5Hash, metadata), or None."""
        try:
            return self.request("GET", f"{API}/b/{bucket}/o/{_q(name)}")
        except GcsError as e:
            if e.code == 404:
                return None
            raise

    def read(self, bucket, name):
        req = urllib.request.Request(f"{API}/b/{bucket}/o/{_q(name)}?alt=media")
        req.add_header("Authorization", self._auth)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read().decode()

    def versions(self, bucket, name):
        """Every generation of the object, live and noncurrent, oldest first (the bucket keeps versions)."""
        out, page = [], ""
        while True:
            res = self.request("GET", f"{API}/b/{bucket}/o?versions=true&prefix={_q(name)}{page}")
            out += [o for o in res.get("items", []) if not name or o["name"] == name]
            if not res.get("nextPageToken"):
                return sorted(out, key=lambda o: int(o["generation"]))
            page = f"&pageToken={_q(res['nextPageToken'])}"


def _crash_if(point):
    if os.environ.get("INTERLOCK_CRASH") != point:
        return
    marker = os.path.join(os.environ["INTERLOCK_CASE_DIR"], "crashed_at")
    if os.path.exists(marker):
        return                                  # one-shot
    with open(marker, "w") as f:
        f.write(str(time.time()))
        f.flush()
        os.fsync(f.fileno())
    os.kill(os.getpid(), signal.SIGKILL)


def write(client, bucket, name, body, metadata, if_generation_match=None):
    """The one agent write path, with the real crash points around it."""
    _crash_if("before_send")
    obj = client.upload(bucket, name, body, metadata, if_generation_match)
    _crash_if("after_commit")
    return obj
