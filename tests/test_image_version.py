"""image_version (build-scripts/image-lib.sh) run against a throwaway repo."""

import os
import subprocess
from pathlib import Path

IMAGE_LIB = Path(__file__).parent.parent / 'build-scripts' / 'image-lib.sh'
GIT_ENV = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}


def _git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], env=GIT_ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(repo, path, text='x'):
    f = repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f.read_text() + text if f.exists() else text)
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-qm', path)


def _version(repo):
    return subprocess.run(['bash', '-c', f'source "{IMAGE_LIB}" && image_version "{repo}"'],
                          env=GIT_ENV, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-qb', 'main')
    (repo / 'purple_tui').mkdir()
    (repo / 'purple_tui' / '__init__.py').write_text('__version__ = "2.0.0"\n')
    _commit(repo, 'build-scripts/00-build-golden-image.sh', 'cp -r /purple-src/purple_tui "$X"\n')
    return repo


def test_counts_only_image_commits(tmp_path):
    repo = _repo(tmp_path)
    assert _version(repo) == 'v2.0.1'
    _commit(repo, 'purple_tui/room.py')
    _commit(repo, 'docs/notes.md')
    _commit(repo, 'studio/app.ts')
    assert _version(repo) == 'v2.0.2'


def test_counts_on_from_the_newest_tag(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, 'tag', 'v2.0.40')
    _commit(repo, 'purple_tui/room.py')
    assert _version(repo) == 'v2.0.41'


def test_nothing_for_uncommitted_or_off_main(tmp_path):
    repo = _repo(tmp_path)
    (repo / 'purple_tui' / 'room.py').write_text('dirty')
    assert _version(repo) == ''
    _git(repo, 'checkout', '-qb', 'lane')
    _commit(repo, 'purple_tui/room.py')
    assert _version(repo) == ''
