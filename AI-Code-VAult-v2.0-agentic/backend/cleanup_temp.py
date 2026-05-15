import os
import shutil
import stat
import time
import tempfile

THRESHOLD_SECONDS = int(os.getenv('CLEANUP_THRESHOLD_SECS', '3600'))  # 1 hour default
PREFIX = 'vault_repo_'


def _win_on_rm_error(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def main():
    temp_dir = tempfile.gettempdir()
    now = time.time()
    removed = []
    skipped = []
    for name in os.listdir(temp_dir):
        if not name.startswith(PREFIX):
            continue
        full = os.path.join(temp_dir, name)
        try:
            if not os.path.isdir(full):
                continue
            mtime = os.path.getmtime(full)
            age = now - mtime
            if age > THRESHOLD_SECONDS:
                try:
                    shutil.rmtree(full, onerror=_win_on_rm_error)
                    removed.append(full)
                except Exception as e:
                    skipped.append((full, str(e)))
            else:
                skipped.append((full, 'Too new'))
        except Exception as e:
            skipped.append((full, str(e)))

    print('Removed:', len(removed))
    for p in removed:
        print(' -', p)
    print('Skipped:', len(skipped))
    for p, reason in skipped:
        print(' -', p, '=>', reason)


if __name__ == '__main__':
    main()
