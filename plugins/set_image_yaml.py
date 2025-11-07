#!/usr/bin/env python3
"""Set image in YAML manifest within Bitbucket repository."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import quote

import yaml

from config_utils import get_env_override
from plugins.shared_helpers import (
    load_auth_file,
    load_netrc_credentials,
    BITBUCKET_ORG,
    fetch_bitbucket_file,
    check_docker_image_exists,
)


class ImageUpdateError(RuntimeError):
    """Error raised when YAML image update fails."""


def _get_git_credentials(auth_data: Dict[str, Any]) -> Dict[str, str]:
    """Extract Git credentials from auth data or netrc."""
    user_keys = ['GIT_USER', 'BITBUCKET_USER', 'BB_USER']
    pass_keys = ['GIT_PASSWORD', 'BITBUCKET_TOKEN', 'BB_PASSWORD']

    username = next((auth_data.get(k) for k in user_keys if auth_data.get(k)), None)
    password = next((auth_data.get(k) for k in pass_keys if auth_data.get(k)), None)

    if not username or not password:
        try:
            netrc_creds = load_netrc_credentials('bitbucket.org')
            username = username or netrc_creds.get('username')
            password = password or netrc_creds.get('password')
        except Exception:
            pass

    if not username or not password:
        raise ImageUpdateError(
            "Bitbucket credentials tidak ditemukan. Pastikan ~/.doq/auth.json "
            "atau ~/.netrc memiliki GIT_USER/GIT_PASSWORD."
        )

    email = auth_data.get('GIT_EMAIL') or f"{username}@users.noreply.bitbucket.org"

    return {
        'username': username,
        'password': password,
        'email': email,
    }


def _extract_yaml_image(data: Any) -> List[str]:
    """Recursively extract all image fields from YAML structure."""
    images = []

    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'image' and isinstance(value, str):
                images.append(value)
            else:
                images.extend(_extract_yaml_image(value))
    elif isinstance(data, list):
        for item in data:
            images.extend(_extract_yaml_image(item))
    return images


def _update_yaml_image(data: Any, new_image: str) -> bool:
    """Recursively update image fields in YAML structure."""
    updated = False

    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'image' and isinstance(value, str):
                data[key] = new_image
                updated = True
            else:
                updated = _update_yaml_image(value, new_image) or updated
    elif isinstance(data, list):
        for item in data:
            updated = _update_yaml_image(item, new_image) or updated
    return updated


def _ensure_branch(repo_dir: Path, refs: str) -> None:
    """Ensure refs is a branch and checked out."""
    # fetch to ensure local refs are up to date
    subprocess.run(['git', 'fetch', 'origin', refs], cwd=repo_dir, check=False, capture_output=True)

    # Determine if refs is a branch
    heads = subprocess.run(
        ['git', 'ls-remote', '--heads', 'origin', refs],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if heads.returncode != 0:
        raise ImageUpdateError(f"Gagal memeriksa refs '{refs}': {heads.stderr.strip()}")

    if not heads.stdout.strip():
        raise ImageUpdateError(
            f"Refs '{refs}' tidak ditemukan sebagai branch. Updating tag tidak didukung."
        )

    checkout = subprocess.run(
        ['git', 'checkout', refs],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if checkout.returncode != 0:
        raise ImageUpdateError(f"Gagal checkout branch '{refs}': {checkout.stderr.strip()}")


def update_image_in_repo(repo: str, refs: str, yaml_path: str, new_image: str, *, dry_run: bool = False) -> Dict[str, Any]:
    """Clone repo, update YAML image, commit, and push.

    Returns dict with success flag and message/details.
    """
    auth_data = load_auth_file()
    
    # Validasi 1: Check image ready di Docker Hub
    print(f"🔍 Memeriksa ketersediaan image: {new_image}")
    image_check = check_docker_image_exists(new_image, auth_data, verbose=False)
    if not image_check.get('exists'):
        error_msg = image_check.get('error', 'Image tidak ditemukan')
        return {
            'success': False,
            'message': f"Image tidak ready di Docker Hub: {error_msg}. Pastikan image sudah di-build dan tersedia.",
        }
    print(f"✅ Image ready: {new_image}")
    
    # Validasi 2: Fetch YAML dari Bitbucket dan bandingkan image
    print(f"🔍 Memeriksa image saat ini di repository...")
    try:
        yaml_content = fetch_bitbucket_file(repo, refs, yaml_path, auth_data)
        current_data = yaml.safe_load(yaml_content)
        
        if current_data:
            current_images = _extract_yaml_image(current_data)
            if current_images:
                # Bandingkan dengan image yang akan di-update
                if new_image in current_images:
                    return {
                        'success': True,
                        'message': f"Image sudah ter-update di repository. Image '{new_image}' sudah sesuai dengan yang ada di {yaml_path}.",
                        'skipped': True,
                    }
                print(f"   Image saat ini: {', '.join(current_images)}")
                print(f"   Image baru: {new_image}")
            else:
                print(f"   ⚠️  Tidak ada field 'image' ditemukan di YAML")
        else:
            print(f"   ⚠️  File YAML kosong atau tidak valid")
    except Exception as e:
        # Jika fetch gagal, lanjutkan dengan clone (mungkin file belum ada atau error sementara)
        print(f"   ⚠️  Tidak dapat memeriksa YAML dari Bitbucket: {e}")
        print(f"   Lanjutkan dengan clone dan update...")
    
    # Lanjutkan dengan clone dan update
    base_tmp = Path(tempfile.gettempdir()) / 'doq-set-image'
    repo_dir = base_tmp / repo

    creds = _get_git_credentials(auth_data)

    org = get_env_override('DOQ_BITBUCKET_ORG') or BITBUCKET_ORG
    os.environ.setdefault('GIT_ASKPASS', 'true')  # avoid interactive prompts

    clone_url = (
        f"https://{quote(creds['username'], safe='')}:{quote(creds['password'], safe='')}"
        f"@bitbucket.org/{org}/{repo}.git"
    )

    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        clone = subprocess.run(
            ['git', 'clone', '--single-branch', '--branch', refs, clone_url, str(repo_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if clone.returncode != 0:
            raise ImageUpdateError(f"Git clone gagal: {clone.stderr.strip()}")

        _ensure_branch(repo_dir, refs)

        target_file = repo_dir / yaml_path
        if not target_file.exists():
            raise ImageUpdateError(f"File YAML '{yaml_path}' tidak ditemukan dalam repository.")

        try:
            with open(target_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ImageUpdateError(f"Gagal membaca YAML: {exc}")

        if data is None:
            raise ImageUpdateError("File YAML kosong atau tidak valid.")

        if not _update_yaml_image(data, new_image):
            return {
                'success': False,
                'message': f"Tidak ada field 'image' yang diperbarui dalam {yaml_path}",
            }

        with open(target_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        if dry_run:
            return {
                'success': True,
                'message': 'Perubahan berhasil disiapkan (dry-run). Tidak ada commit/push.',
            }

        # Stage changes
        subprocess.run(['git', 'config', 'user.name', creds['username']], cwd=repo_dir, check=False)
        subprocess.run(['git', 'config', 'user.email', creds['email']], cwd=repo_dir, check=False)

        diff = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_dir, capture_output=True, text=True)
        if not diff.stdout.strip():
            return {
                'success': False,
                'message': 'Tidak ada perubahan yang perlu di-commit.',
            }

        subprocess.run(['git', 'add', yaml_path], cwd=repo_dir, check=True)

        commit_msg = f"chore: update image to {new_image}"
        commit = subprocess.run(['git', 'commit', '-m', commit_msg], cwd=repo_dir, capture_output=True, text=True)
        if commit.returncode != 0:
            raise ImageUpdateError(f"Gagal commit perubahan: {commit.stderr.strip()}")

        push = subprocess.run(['git', 'push', 'origin', f"HEAD:{refs}"], cwd=repo_dir, capture_output=True, text=True)
        if push.returncode != 0:
            raise ImageUpdateError(f"Gagal push ke origin: {push.stderr.strip()}")

        return {
            'success': True,
            'message': f"Image berhasil diperbarui ke {new_image} dan push ke {refs}.",
            'commit': commit.stdout.strip(),
        }

    finally:
        # Cleanup cloned repository
        if repo_dir.exists():
            shutil.rmtree(repo_dir)

