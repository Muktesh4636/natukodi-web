# Gunduata.club website frontend

Static landing page for **gunduata.club**. Nginx is configured to serve this folder as the site root (path on server: `/root/apk_of_ata/frontend`) and to proxy `/api/`, `/admin/`, `/ws/`, `/static/`, `/media/` to the Django backend.

## Deploy

On deploy, `git pull` updates this folder on the server; Nginx already points at it. No separate copy step. Ensure `index.html` is in the repo; add `apk/Gundu Ata.apk` and `videos/gameplay.mp4` on the server or in the repo as needed.

## Structure

- `index.html` — landing page
- `apk/` — place APK file(s) here for download links
- `videos/` — place `gameplay.mp4` here for the hero video
