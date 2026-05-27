#!/usr/bin/env python3

import json
import html
import mimetypes
import re
import ssl
import sys
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode, urlparse, unquote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ----------------------------
# Rocket.Chat settings
# ----------------------------
RC_SERVER = "https://chat.example.com"
RC_AUTH_TOKEN = "PASTE_YOUR_TOKEN_HERE"
RC_USER_ID = "PASTE_YOUR_ROCKETCHAT_USER_ID_HERE"

# Rocket.Chat appears to cap history responses at 200 messages.
COUNT = 200

# Your server rate-limits
REQUEST_DELAY_SECONDS = 60

# Set this to True only if Python has local SSL certificate issues.
ALLOW_INSECURE_SSL = False

# Output folders
OUTDIR = Path("rocketchat_exports")
JSON_DIR = OUTDIR / "json"
HTML_DIR = OUTDIR / "html"
ATTACHMENTS_DIR = OUTDIR / "attachments"

JSON_DIR.mkdir(parents=True, exist_ok=True)
HTML_DIR.mkdir(parents=True, exist_ok=True)
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------
# API helpers
# ----------------------------

def first_string(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def make_url(endpoint_or_url, query_params=None):
    if not isinstance(endpoint_or_url, str) or not endpoint_or_url.strip():
        raise ValueError(
            f"Expected URL/path string, got {type(endpoint_or_url).__name__}: {endpoint_or_url!r}"
        )

    endpoint_or_url = endpoint_or_url.strip()

    if endpoint_or_url.startswith("http://") or endpoint_or_url.startswith("https://"):
        base = endpoint_or_url
    elif endpoint_or_url.startswith("/"):
        base = f"{RC_SERVER.rstrip('/')}{endpoint_or_url}"
    else:
        base = f"{RC_SERVER.rstrip('/')}/api/v1/{endpoint_or_url}"

    if query_params:
        return base + "?" + urlencode(query_params)

    return base


def urlopen_with_optional_ssl(request):
    if ALLOW_INSECURE_SSL:
        context = ssl._create_unverified_context()
        return urlopen(request, context=context)

    return urlopen(request)


def api_get(endpoint, query_params=None):
    try:
        url = make_url(endpoint, query_params)
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }

    request = Request(
        url,
        headers={
            "X-Auth-Token": RC_AUTH_TOKEN,
            "X-User-Id": RC_USER_ID,
            "accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen_with_optional_ssl(request) as response:
            body = response.read().decode("utf-8")

        return json.loads(body)

    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except Exception:
            return {
                "success": False,
                "error": f"HTTP error {e.code}",
                "raw": body,
            }

    except URLError as e:
        return {
            "success": False,
            "error": f"Network error: {e.reason}",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def api_download_file(file_url, outfile):
    """
    Downloads a Rocket.Chat attachment using auth headers.

    file_url may be:
      /file-upload/abc123/image.png
      https://chat.example.com/file-upload/abc123/image.png

    Some Rocket.Chat attachment fields can be booleans, so this rejects
    anything that is not a real string URL/path.
    """
    if not isinstance(file_url, str) or not file_url.strip():
        return False, f"Missing or invalid file URL: {file_url!r}"

    try:
        url = make_url(file_url)
    except Exception as e:
        return False, str(e)

    request = Request(
        url,
        headers={
            "X-Auth-Token": RC_AUTH_TOKEN,
            "X-User-Id": RC_USER_ID,
            "accept": "*/*",
        },
        method="GET",
    )

    try:
        with urlopen_with_optional_ssl(request) as response:
            content = response.read()
            content_type = response.headers.get("content-type", "")

        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_bytes(content)

        return True, {
            "contentType": content_type,
            "bytes": len(content),
            "url": url,
        }

    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP error {e.code}: {body[:200]}"

    except URLError as e:
        return False, f"Network error: {e.reason}"

    except Exception as e:
        return False, str(e)


def sleep_between_requests(reason):
    print(f"    Waiting {REQUEST_DELAY_SECONDS} seconds {reason}...")
    time.sleep(REQUEST_DELAY_SECONDS)


# ----------------------------
# Formatting helpers
# ----------------------------

def safe_name(value):
    value = value or "unnamed"
    value = unquote(str(value))
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:120].strip("_") or "unnamed"


def endpoint_for_type(room_type):
    if room_type == "c":
        return "channels.history"
    if room_type == "p":
        return "groups.history"
    if room_type == "d":
        return "im.history"
    return None


def room_type_label(room_type):
    return {
        "c": "channel",
        "p": "private group",
        "d": "direct message",
    }.get(room_type, room_type or "unknown")


def room_name(room):
    return (
        room.get("name")
        or room.get("fname")
        or ",".join(room.get("usernames", []))
        or room.get("_id")
        or "unnamed"
    )


def fmt_time(value):
    if isinstance(value, dict):
        value = value.get("$date")

    if not value:
        return ""

    try:
        value = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def linkify(text):
    escaped = html.escape(text or "")
    url_re = re.compile(r"(https?://[^\s<]+)")
    return url_re.sub(
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
        escaped,
    )


def is_image_file(path_or_name, content_type=None):
    if content_type and str(content_type).lower().startswith("image/"):
        return True

    suffix = Path(str(path_or_name)).suffix.lower()
    return suffix in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".svg",
        ".tif",
        ".tiff",
    }


def guess_extension_from_url(url):
    if not isinstance(url, str) or not url.strip():
        return ""

    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix

    if suffix:
        return suffix

    return ""


def ensure_filename_has_extension(filename, url=None, content_type=None):
    path = Path(filename)

    if path.suffix:
        return filename

    if url:
        ext = guess_extension_from_url(url)
        if ext:
            return filename + ext

    if content_type:
        guessed = mimetypes.guess_extension(str(content_type).split(";")[0].strip())
        if guessed:
            return filename + guessed

    return filename


def html_rel_attachment_path(local_path):
    """
    HTML files are in rocketchat_exports/html.
    Attachments are in rocketchat_exports/attachments.
    So relative path should start with ../attachments/...
    """
    try:
        return Path("../attachments") / local_path.relative_to(ATTACHMENTS_DIR)
    except Exception:
        return local_path


# ----------------------------
# Attachment extraction/download
# ----------------------------

def extract_attachment_candidates(msg):
    """
    Pull likely downloadable URLs from Rocket.Chat message fields.

    Some fields can be booleans, so this only keeps real string URLs/paths.
    """
    candidates = []

    for file_obj in msg.get("files", []) or []:
        if not isinstance(file_obj, dict):
            continue

        name = first_string(
            file_obj.get("name"),
            file_obj.get("title"),
            file_obj.get("_id"),
        ) or "file"

        url = first_string(
            file_obj.get("url"),
            file_obj.get("path"),
            file_obj.get("link"),
        )

        if url:
            candidates.append({
                "label": "File",
                "name": name,
                "url": url,
                "contentType": first_string(file_obj.get("type"), file_obj.get("mimeType")),
                "description": None,
            })

    for att in msg.get("attachments", []) or []:
        if not isinstance(att, dict):
            continue

        title = first_string(
            att.get("title"),
            att.get("description"),
            att.get("text"),
        ) or "attachment"

        possible_urls = [
            att.get("title_link_download"),
            att.get("title_link"),
            att.get("image_url"),
            att.get("image_preview"),
            att.get("thumb_url"),
            att.get("url"),
        ]

        for raw_url in possible_urls:
            url = first_string(raw_url)
            if url:
                candidates.append({
                    "label": "Attachment",
                    "name": title,
                    "url": url,
                    "contentType": None,
                    "description": first_string(att.get("description")),
                })

    # De-duplicate by URL
    seen = set()
    unique = []

    for item in candidates:
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue

        if url in seen:
            continue

        seen.add(url)
        unique.append(item)

    return unique


def attachment_html(msg, room_attachment_dir, downloaded_attachments):
    parts = []
    candidates = extract_attachment_candidates(msg)

    for idx, item in enumerate(candidates, start=1):
        label = item.get("label") or "Attachment"
        name = item.get("name") or "attachment"
        url = item.get("url")
        content_type = item.get("contentType")

        if not isinstance(url, str) or not url.strip():
            continue

        msg_id = safe_name(msg.get("_id") or "message")
        base_filename = safe_name(name)

        if not Path(base_filename).suffix:
            base_filename = ensure_filename_has_extension(
                base_filename,
                url=url,
                content_type=content_type,
            )

        local_file = room_attachment_dir / f"{msg_id}__{idx}__{base_filename}"

        ok, result = api_download_file(url, local_file)

        if ok:
            actual_content_type = result.get("contentType") if isinstance(result, dict) else content_type

            new_name = ensure_filename_has_extension(
                local_file.name,
                url=url,
                content_type=actual_content_type,
            )
            new_file = local_file.with_name(new_name)

            if local_file.exists() and local_file != new_file:
                local_file.rename(new_file)

            local_file = new_file

            rel = html_rel_attachment_path(local_file)
            rel_str = str(rel).replace("\\", "/")

            downloaded_attachments.append({
                "messageId": msg.get("_id"),
                "name": name,
                "url": url,
                "localFile": str(local_file),
                "contentType": actual_content_type,
                "bytes": result.get("bytes") if isinstance(result, dict) else None,
            })

            if is_image_file(local_file, actual_content_type):
                parts.append(
                    f'<div class="attachment">'
                    f'<div>{html.escape(label)}: '
                    f'<a href="{html.escape(rel_str)}" target="_blank" rel="noopener noreferrer">'
                    f'{html.escape(name)}</a></div>'
                    f'<img class="inline-image" src="{html.escape(rel_str)}" alt="{html.escape(name)}">'
                    f'</div>'
                )
            else:
                parts.append(
                    f'<div class="attachment">{html.escape(label)}: '
                    f'<a href="{html.escape(rel_str)}" target="_blank" rel="noopener noreferrer">'
                    f'{html.escape(name)}</a></div>'
                )

        else:
            parts.append(
                f'<div class="attachment">{html.escape(label)}: {html.escape(name)} '
                f'<span class="download-error">(could not download: {html.escape(str(result))})</span>'
                f'</div>'
            )

        description = item.get("description")
        if description:
            parts.append(f'<div class="attachment-desc">{linkify(description)}</div>')

        # Attachment downloads also count as server requests.
        sleep_between_requests("before next attachment/request")

    return "\n".join(parts)


# ----------------------------
# HTML building
# ----------------------------

def message_html(msg, room_attachment_dir, downloaded_attachments):
    user = msg.get("u") or {}
    username = user.get("username") or user.get("name") or "unknown"
    timestamp = fmt_time(msg.get("ts"))

    text = msg.get("msg") or ""
    text_html = linkify(text).replace("\n", "<br>")

    edited = ""
    if msg.get("editedAt"):
        edited = f'<span class="edited">edited {html.escape(fmt_time(msg.get("editedAt")))}</span>'

    system_type = msg.get("t")
    system_label = ""
    if system_type:
        system_label = f'<span class="system-type">{html.escape(system_type)}</span>'

    return f"""
    <div class="message">
      <div class="meta">
        <span class="user">{html.escape(username)}</span>
        <span class="time">{html.escape(timestamp)}</span>
        {system_label}
        {edited}
      </div>
      <div class="body">{text_html}</div>
      {attachment_html(msg, room_attachment_dir, downloaded_attachments)}
    </div>
    """


def build_html(title, source_file, data, room_type=None, rid=None, room_attachment_dir=None):
    messages = data.get("messages", [])

    # Rocket.Chat history endpoints usually return newest-first.
    # Reversing makes the transcript oldest-first.
    messages = list(reversed(messages))

    downloaded_attachments = []
    items = "\n".join(
        message_html(msg, room_attachment_dir, downloaded_attachments)
        for msg in messages
    )

    data["downloadedAttachments"] = downloaded_attachments

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  margin: 32px;
  max-width: 980px;
  line-height: 1.45;
  color: #1f2328;
}}
h1 {{
  margin-bottom: 4px;
}}
.summary {{
  color: #666;
  margin-bottom: 24px;
}}
.message {{
  border-bottom: 1px solid #eaecef;
  padding: 12px 0;
}}
.meta {{
  margin-bottom: 5px;
  font-size: 14px;
}}
.user {{
  font-weight: 700;
}}
.time, .edited {{
  color: #6a737d;
  margin-left: 8px;
}}
.system-type {{
  color: #8250df;
  background: #f6f0ff;
  border-radius: 999px;
  padding: 2px 7px;
  margin-left: 8px;
  font-size: 12px;
}}
.body {{
  word-wrap: break-word;
}}
.attachment, .attachment-desc {{
  margin-top: 8px;
  padding: 8px 10px;
  border-left: 3px solid #d0d7de;
  background: #f6f8fa;
}}
.inline-image {{
  display: block;
  max-width: 720px;
  max-height: 480px;
  margin-top: 8px;
  border-radius: 6px;
  border: 1px solid #d0d7de;
}}
.download-error {{
  color: #9a3412;
}}
a {{
  color: #0969da;
}}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="summary">
  Room ID: {html.escape(rid or "")}<br>
  Room type: {html.escape(room_type_label(room_type))}<br>
  Source JSON: {html.escape(str(source_file))}<br>
  Messages: {len(messages)}<br>
  Downloaded attachments: {len(downloaded_attachments)}
</div>
{items}
</body>
</html>
"""


# ----------------------------
# Message fetching
# ----------------------------

def fetch_all_messages(endpoint, rid):
    all_messages = []
    offset = 0
    page_count = 0

    while True:
        print(f"    Fetching messages offset={offset}, count={COUNT}")

        data = api_get(endpoint, {
            "roomId": rid,
            "count": COUNT,
            "offset": offset,
        })

        page_count += 1

        if not data.get("success"):
            return data

        messages = data.get("messages", [])
        all_messages.extend(messages)

        print(f"    Got {len(messages)} messages; total so far: {len(all_messages)}")

        if len(messages) < COUNT:
            break

        offset += COUNT
        sleep_between_requests("before next page")

    data["messages"] = all_messages
    data["count"] = len(all_messages)
    data["pagesFetched"] = page_count
    return data


# ----------------------------
# Index
# ----------------------------

def write_index(manifest):
    links = []

    for item in manifest:
        if item.get("success") and item.get("htmlFile"):
            html_path = Path(item["htmlFile"])
            links.append(
                f'<li><a href="{html.escape(html_path.name)}">{html.escape(item["name"])}</a> '
                f'({html.escape(room_type_label(item.get("type")))}, '
                f'{item.get("messageCount")} messages, '
                f'{item.get("attachmentCount", 0)} attachment(s), '
                f'{item.get("pagesFetched")} page(s))</li>'
            )

    failures = []

    for item in manifest:
        if not item.get("success"):
            failures.append(
                f'<li>{html.escape(item.get("name") or "unnamed")} '
                f'({html.escape(item.get("rid") or "")}): '
                f'{html.escape(item.get("error") or "Unknown error")}</li>'
            )

    index_file = HTML_DIR / "index.html"

    index_file.write_text(f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Rocket.Chat HTML Export</title>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  margin: 32px;
  max-width: 900px;
  line-height: 1.45;
}}
li {{
  margin: 6px 0;
}}
.failures {{
  margin-top: 32px;
  color: #9a3412;
}}
</style>
</head>
<body>
<h1>Rocket.Chat HTML Export</h1>
<p>Exported {len(links)} readable room transcript(s).</p>

<h2>Rooms</h2>
<ul>
{chr(10).join(links)}
</ul>

<div class="failures">
<h2>Failures / skipped rooms</h2>
<ul>
{chr(10).join(failures) if failures else "<li>None</li>"}
</ul>
</div>
</body>
</html>
""", encoding="utf-8")

    return index_file


# ----------------------------
# Main
# ----------------------------

def main():
    print("Checking login...")

    me = api_get("me")
    if not me.get("success"):
        print("Login failed:")
        print(json.dumps(me, indent=2))
        sys.exit(1)

    print("Login OK")
    sleep_between_requests("before fetching rooms")

    print("Fetching visible rooms...")

    rooms_response = api_get("rooms.get")
    (JSON_DIR / "rooms_get_response.json").write_text(
        json.dumps(rooms_response, indent=2),
        encoding="utf-8",
    )

    if not rooms_response.get("success"):
        print("Could not fetch rooms:")
        print(json.dumps(rooms_response, indent=2))
        sys.exit(1)

    rooms = rooms_response.get("update", [])
    print(f"Found {len(rooms)} rooms")

    sleep_between_requests("before first room download")

    manifest = []

    for index, room in enumerate(rooms, start=1):
        rid = room.get("_id")
        room_type = room.get("t")
        name = room_name(room)
        endpoint = endpoint_for_type(room_type)

        if not rid:
            print(f"[{index}/{len(rooms)}] Skipping room with no _id")
            manifest.append({
                "rid": None,
                "name": name,
                "type": room_type,
                "success": False,
                "error": "Room has no _id",
            })
            continue

        if not endpoint:
            print(f"[{index}/{len(rooms)}] Skipping {name} ({rid}); unsupported type: {room_type}")
            manifest.append({
                "rid": rid,
                "name": name,
                "type": room_type,
                "success": False,
                "error": f"Unsupported room type: {room_type}",
            })
            continue

        base_name = f"{safe_name(name)}__{rid}"
        json_file = JSON_DIR / f"{base_name}.json"
        html_file = HTML_DIR / f"{base_name}.html"
        room_attachment_dir = ATTACHMENTS_DIR / base_name
        room_attachment_dir.mkdir(parents=True, exist_ok=True)

        print(f"[{index}/{len(rooms)}] Downloading {name} ({rid}) via {endpoint}")

        data = fetch_all_messages(endpoint, rid)

        success = data.get("success")
        message_count = len(data.get("messages", [])) if isinstance(data.get("messages"), list) else None
        pages_fetched = data.get("pagesFetched")
        attachment_count = 0

        if success:
            html_text = build_html(
                name,
                json_file,
                data,
                room_type=room_type,
                rid=rid,
                room_attachment_dir=room_attachment_dir,
            )

            attachment_count = len(data.get("downloadedAttachments", []))

            # Write JSON after attachment download, so downloadedAttachments is included.
            json_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            html_file.write_text(html_text, encoding="utf-8")

            print(f"    Wrote JSON: {json_file}")
            print(f"    Wrote HTML: {html_file}")
            print(f"    Downloaded attachments: {attachment_count}")

        else:
            json_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"    Failed: {data.get('error') or data.get('message')}")

        manifest.append({
            "rid": rid,
            "name": name,
            "type": room_type,
            "endpoint": endpoint,
            "jsonFile": str(json_file),
            "htmlFile": str(html_file) if success else None,
            "attachmentsDir": str(room_attachment_dir) if success else None,
            "success": success,
            "messageCount": message_count,
            "attachmentCount": attachment_count,
            "pagesFetched": pages_fetched,
            "error": data.get("error") or data.get("message"),
        })

        manifest_file = JSON_DIR / "download_manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        write_index(manifest)

        if index < len(rooms):
            sleep_between_requests("before next room")

    index_file = write_index(manifest)

    print()
    print("Done.")
    print(f"JSON files: {JSON_DIR}")
    print(f"HTML files: {HTML_DIR}")
    print(f"Attachments: {ATTACHMENTS_DIR}")
    print(f"Manifest: {JSON_DIR / 'download_manifest.json'}")
    print(f"Open this file in your browser: {index_file}")


if __name__ == "__main__":
    main()