#!/usr/bin/env python3
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime
import json, re, shutil, subprocess
from inbox_index import managed_info

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "library.config.json"
TEMPLATE_PATH = ROOT / "assets" / "category-index.html"

class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.title_parts = []
        self.h1_parts = []
        self.in_title = False
        self.in_h1 = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "meta":
            name = (attrs.get("name") or "").strip().lower()
            content = (attrs.get("content") or "").strip()
            if name:
                self.meta[name] = content
        elif tag == "title":
            self.in_title = True
        elif tag == "h1" and not self.h1_parts:
            self.in_h1 = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.in_h1 = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.in_h1:
            self.h1_parts.append(data)

    @property
    def title(self):
        return " ".join("".join(self.title_parts).split())

    @property
    def h1(self):
        return " ".join("".join(self.h1_parts).split())

def read_html_info(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    parser = MetaParser()
    parser.feed(text)

    meta = parser.meta
    title = (
        meta.get("library-title")
        or parser.title
        or parser.h1
        or path.stem
    )
    # Remove a common suffix from <title> fallback.
    if "library-title" not in meta and " | " in title:
        title = title.split(" | ", 1)[0].strip()

    description = (
        meta.get("library-description")
        or meta.get("description")
        or ""
    )
    group = meta.get("library-group") or "未分類"

    tags_raw = meta.get("library-tags") or ""
    tags = [x.strip() for x in re.split(r"[,、]", tags_raw) if x.strip()]

    pinned = (meta.get("library-pinned") or "").lower() in {"1","true","yes","on"}
    hidden = (meta.get("library-hidden") or "").lower() in {"1","true","yes","on"}

    try:
        order = int(meta.get("library-order") or 999999)
    except ValueError:
        order = 999999

    return {
        "title": title,
        "description": description,
        "group": group,
        "tags": tags,
        "pinned": pinned,
        "hidden": hidden,
        "order": order,
    }

def read_item_media(path: Path, category_dir: Path, fallback_alt: str):
    meta_path = path.parent / "meta.json"
    if not meta_path.is_file():
        return {}

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    files = meta.get("files") if isinstance(meta.get("files"), dict) else {}

    # A folder can contain multiple HTML files. Only use media belonging to
    # the guide currently being indexed.
    if files.get("guide") != path.name:
        return {}

    def existing_media_file(name):
        if not isinstance(name, str) or not name.strip():
            return None

        candidate = (path.parent / name).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
            relative = candidate.relative_to(category_dir.resolve())
        except ValueError:
            return None

        if not candidate.is_file():
            return None
        return relative.as_posix()

    preview = existing_media_file(files.get("preview"))
    thumbnail = existing_media_file(files.get("thumbnail")) or preview
    if not thumbnail and not preview:
        return {}

    media = meta.get("media") if isinstance(meta.get("media"), dict) else {}
    thumbnail_meta = media.get("thumbnail") if isinstance(media.get("thumbnail"), dict) else {}
    preview_meta = media.get("preview") if isinstance(media.get("preview"), dict) else {}
    alt = thumbnail_meta.get("alt") or preview_meta.get("alt") or fallback_alt

    result = {"thumbnail_alt": alt}
    if thumbnail:
        result["thumbnail"] = thumbnail
    if preview:
        result["preview"] = preview
    return result

def git_updated(path: Path):
    rel = path.relative_to(ROOT).as_posix()
    try:
        value = subprocess.check_output(
            ["git", "log", "-1", "--format=%cs", "--", rel],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if value:
            return value
    except Exception:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")

def git_tracked_files():
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
        return {item for item in output.split("\0") if item}
    except Exception:
        return None

def write_json(path: Path, payload):
    existing_text = path.read_text(encoding="utf-8") if path.is_file() else None
    if existing_text is not None:
        try:
            existing = json.loads(existing_text)
            existing_content = {key: value for key, value in existing.items() if key != "generated_at"}
            new_content = {key: value for key, value in payload.items() if key != "generated_at"}
            if existing_content == new_content and existing.get("generated_at"):
                payload = dict(payload)
                payload["generated_at"] = existing["generated_at"]
        except (json.JSONDecodeError, AttributeError):
            pass

    new_text = json.dumps(payload, ensure_ascii=False, indent=2)
    if existing_text != new_text:
        path.write_text(new_text, encoding="utf-8")

def build():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    tracked_files = git_tracked_files()

    all_items = []
    categories_out = []

    for folder, category in config["categories"].items():
        category_dir = ROOT / folder
        category_dir.mkdir(parents=True, exist_ok=True)

        # Keep every category index identical.
        (category_dir / "index.html").write_text(template, encoding="utf-8")

        items = []
        for path in sorted(category_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".html", ".htm"}:
                continue
            managed = managed_info(path, category_dir)
            if managed is not None and managed.get("skip"):
                continue
            if path.name.lower() == "index.html" and managed is None:
                continue
            if tracked_files is not None and path.relative_to(ROOT).as_posix() not in tracked_files:
                continue

            info = read_html_info(path)
            if managed is not None:
                info.update(managed["info"])
            if info["hidden"]:
                continue

            rel = path.relative_to(category_dir).as_posix()
            item = {
                "title": info["title"],
                "description": info["description"],
                "group": info["group"],
                "tags": info["tags"],
                "pinned": info["pinned"],
                "order": info["order"],
                "updated": git_updated(path),
                "file": rel,
            }
            item.update(managed["media"] if managed is not None else read_item_media(path, category_dir, info["title"]))
            items.append(item)

        # Pinned first, explicit order, recent date, title.
        items.sort(key=lambda x: (
            0 if x["pinned"] else 1,
            x["order"],
            "" if x["updated"] is None else "".join(chr(255-ord(c)) if ord(c)<256 else c for c in x["updated"]),
            x["title"],
        ))

        payload = {
            "category": {
                "folder": folder,
                "title": category.get("title", folder),
                "icon": category.get("icon", "📚"),
                "description": category.get("description", ""),
                "accent": category.get("accent", "#2867d8"),
            },
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "items": items,
        }
        write_json(category_dir / "library.json", payload)

        categories_out.append({
            "folder": folder,
            "title": category.get("title", folder),
            "icon": category.get("icon", "📚"),
            "description": category.get("description", ""),
            "accent": category.get("accent", "#2867d8"),
            "count": len(items),
        })

        for item in items:
            global_item = dict(item)
            global_item["category_folder"] = folder
            global_item["category_title"] = category.get("title", folder)
            global_item["category_icon"] = category.get("icon", "📚")
            global_item["url"] = f"./{folder}/{item['file']}"
            if item.get("thumbnail"):
                global_item["thumbnail_url"] = f"./{folder}/{item['thumbnail']}"
            if item.get("preview"):
                global_item["preview_url"] = f"./{folder}/{item['preview']}"
            all_items.append(global_item)

    # Global newest-first index.
    all_items.sort(key=lambda x: (
        0 if x["pinned"] else 1,
        x["updated"] or "",
        x["title"]
    ), reverse=False)

    # Put pinned first, then newest.
    pinned = [x for x in all_items if x["pinned"]]
    normal = [x for x in all_items if not x["pinned"]]
    pinned.sort(key=lambda x: (x["order"], x["title"]))
    normal.sort(key=lambda x: (x["updated"] or "", x["title"]), reverse=True)
    all_items = pinned + normal

    global_payload = {
        "site_title": config.get("site_title", "My Library"),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "categories": categories_out,
        "items": all_items,
    }
    write_json(ROOT / "library-all.json", global_payload)

    print(f"Generated {len(categories_out)} categories / {len(all_items)} items.")

if __name__ == "__main__":
    build()
