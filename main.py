import requests
import json
import os

# ===== CONFIGURATION =====
TENANT_ID = "12b46b3d-02dd-4918-ba72-67e70d056a02"
CLIENT_ID = "505788fb-9b59-4aa2-b7e4-e46b6c09bfe1"
CLIENT_SECRET = "xxxx"
SITE_NAME = "test"
SITE_DOMAIN = "banhcamvinh.sharepoint.com"

OUTPUT_ROOT_BASE = "downloaded_files"
DELTA_ROOT_BASE = "delta_data"

folder_path = "test1"


def get_access_token():
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    token_data = {
        "grant_type": "client_credentials",
        "CLIENT_ID": CLIENT_ID,
        "CLIENT_SECRET": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default"
    }
    r = requests.post(token_url, data=token_data)
    r.raise_for_status()
    return r.json()["access_token"]


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def save_delta_link(delta_link, folder_path):
    os.makedirs(os.path.dirname(
        f"{DELTA_ROOT_BASE}/{folder_path}.json"), exist_ok=True)
    with open(f"{DELTA_ROOT_BASE}/{folder_path}.json", "w") as fh:
        json.dump({"deltaLink": delta_link}, fh)


def load_delta_link(folder_path):
    if os.path.exists(f"{DELTA_ROOT_BASE}/{folder_path}.json"):
        try:
            j = json.load(open(f"{DELTA_ROOT_BASE}/{folder_path}.json"))
            return j.get("deltaLink")
        except Exception:
            return None
    return None


def relative_path_from_parent(parent_path, drive_root_marker="/root:"):
    """
    parent_path examples:
      "/drive/root:/testing/subfolder"
      "/drives/{id}/root:/testing/subfolder"
    We want the path relative to root: -> "/testing/subfolder"
    Returns without leading slash: "testing/subfolder"
    """
    if not parent_path:
        return ""
    # find 'root:' marker
    marker = "root:"
    if marker in parent_path:
        rel = parent_path.split(marker, 1)[1]
    else:
        # fallback: use entire path and strip drive related parts
        rel = parent_path
    # remove leading/trailing slashes/colons
    rel = rel.strip(":/")
    return rel


def download_file_by_download_url(download_url, out_path):
    r = requests.get(download_url, stream=True)
    r.raise_for_status()
    with open(out_path, "wb") as fh:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)


def download_file_by_item_content(drive_id, item_id, headers, out_path):
    # GET /drives/{drive_id}/items/{item_id}/content
    content_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content"
    r = requests.get(content_url, headers=headers, stream=True)
    r.raise_for_status()
    with open(out_path, "wb") as fh:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)


# ===== MAIN =====
def sync_folder(folder_path):
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1) Resolve site ID
    site_api = f"https://graph.microsoft.com/v1.0/sites/{SITE_DOMAIN}:/sites/{SITE_NAME}"
    r = requests.get(site_api, headers=headers)
    r.raise_for_status()
    site_id = r.json()["id"]

    # 2) Get drive
    drive_api = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    r = requests.get(drive_api, headers=headers)
    r.raise_for_status()
    drives = r.json().get("value", [])
    if not drives:
        raise RuntimeError("No drives found on site")
    drive_id = drives[0]["id"]

    # 3) Determine delta start url
    delta_link = load_delta_link(folder_path)

    if delta_link:
        print("🔁 Using saved deltaLink for incremental sync...")
        api_url = delta_link
    else:
        print("📂 First-time run -> full sync via delta endpoint...")
        api_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}:/delta"

    changed_files = []     # (file metadata dict)
    deleted_items = []     # for tracking deletes
    next_delta_link = None

    # 4) Walk pages of delta/nextLink
    while api_url:
        r = requests.get(api_url, headers=headers)
        r.raise_for_status()
        data = r.json()

        for item in data.get("value", []):
            # deleted items: if '@removed' in item then it's a delete event
            if item.get("@removed"):
                deleted_items.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "parentPath": item.get("parentReference", {}).get("path"),
                    "reason": item["@removed"].get("reason")
                })
                continue

            # only handle files (skip folders)
            if "file" not in item:
                # could be folder metadata or other change; 
                # skip but you may want to create folder on destination
                continue

            # parentReference.path example: "/drive/root:/testing/..."
            # or "/drives/{id}/root:/testing/..."
            parent_path = item.get("parentReference", {}).get("path", "")
            rel_parent = relative_path_from_parent(parent_path)
            # desired relative path under the configured folder_path:
            # if rel_parent starts with folder_path, remove it to get subpath; 
            # else keep whole rel_parent
            # normalize both
            rel_parent_norm = rel_parent.lstrip("/")
            folder_norm = folder_path.strip("/")
            if rel_parent_norm.startswith(folder_norm):
                # path under the folder_path
                sub_rel = rel_parent_norm[len(folder_norm):].lstrip("/")
            else:
                # if item located somewhere else (unlikely)
                # , keep full rel_parent
                sub_rel = rel_parent_norm

            # build final relative path to write
            # (folder_path + sub_rel + filename)
            if sub_rel:
                relative_file_path = os.path.join(folder_norm, sub_rel, item.get("name"))
            else:
                relative_file_path = os.path.join(folder_norm, item.get("name"))

            # download url might not exist for some items (rare)
            #  => fallback to content by item id
            download_url = item.get("@microsoft.graph.downloadUrl")
            changed_files.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "relative_path": relative_file_path.replace("\\", "/"),
                # use forward slashes
                "downloadUrl": download_url,
                "driveId": drive_id
            })

        # nextLink or deltaLink handling
        api_url = data.get("@odata.nextLink")
        # Save deltaLink from response (might be present only in last page)
        if data.get("@odata.deltaLink"):
            next_delta_link = data.get("@odata.deltaLink")

    # 5) Persist delta link for next run
    if next_delta_link:
        save_delta_link(next_delta_link, folder_path)
        print("💾 Saved deltaLink for next incremental sync.")

    # 6) Download changed files preserving folder structure
    print(f"✅ Found {len(changed_files)} changed/added files.")
    for f in changed_files:
        out_full_path = os.path.join(OUTPUT_ROOT_BASE, f["relative_path"])
        out_dir = os.path.dirname(out_full_path)
        ensure_dir(out_dir)

        try:
            if f["downloadUrl"]:
                download_file_by_download_url(f["downloadUrl"], out_full_path)
            else:
                # fallback: use item content endpoint
                download_file_by_item_content(
                    f["driveId"],
                    f["id"],
                    headers,
                    out_full_path)
            print(f"⬇️ Downloaded: {f['relative_path']}")
        except Exception as ex:
            print(f"❌ Failed to download {f['relative_path']}: {ex}")

    # 7) Print deleted items so you can remove them from destination if needed
    if deleted_items:
        print("Deleted items detected(you may want to remove from des)")
        for d in deleted_items:
            print("-", d)


sync_folder(folder_path)
