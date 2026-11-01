"""Use exact approved reference bytes; never substitute approximate regeneration."""
from pathlib import Path
import hashlib,shutil,os
EXPECTED='69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913'
def main():
    root=Path(__file__).resolve().parents[2];source=Path(os.environ.get('APPROVED_HEIGHTFIELD_SOURCE',root/'assets/approved/heightfield.npz'));target=root/'terrain/rolling_uneven/v1/heightfield.npz'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('Reference heightfield checksum mismatch')
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=EXPECTED:
        digest=hashlib.sha256(target.read_bytes()).hexdigest();rejected=root/'reports/generated/terrain'/('rejected-'+digest+'.npz');rejected.parent.mkdir(parents=True,exist_ok=True)
        if not rejected.exists():shutil.copy2(target,rejected)
    shutil.copy2(source,target);print('Verified approved reference NPZ:',EXPECTED)
if __name__=='__main__':main()
