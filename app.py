"""
Google Drive File Copy – Streamlit app.
Copy selected files (by comma-separated names) from a source folder to a destination folder.
"""
# Apply TLS 1.2+ fix before any other imports that might use SSL (avoids WRONG_VERSION_NUMBER).
import ssl
_orig = ssl.create_default_context
def _tls12_context():
    ctx = _orig()
    if hasattr(ssl, "TLSVersion") and hasattr(ctx, "minimum_version"):
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx
ssl.create_default_context = _tls12_context

import base64
import io
import streamlit as st
import streamlit.components.v1 as components
from drive_service import (
    get_drive_service,
    build_folder_paths,
    list_files_in_folder,
    resolve_names_to_file_ids,
    copy_file_to_folder,
    get_file_metadata,
    get_file_content,
    CREDENTIALS_PATH,
    TOKEN_PATH,
)
import os


def init_session_state():
    if "drive_service" not in st.session_state:
        st.session_state.drive_service = None
    if "source_folder_id" not in st.session_state:
        st.session_state.source_folder_id = None
    if "dest_folder_id" not in st.session_state:
        st.session_state.dest_folder_id = None
    if "source_files_cache" not in st.session_state:
        st.session_state.source_files_cache = None  # (folder_id, list of {id, name, mimeType})
    if "source_files_cache_id" not in st.session_state:
        st.session_state.source_files_cache_id = None


def ensure_authenticated():
    """Build Drive service if credentials exist; return True if ready."""
    if st.session_state.drive_service is not None:
        return True
    if not os.path.exists(CREDENTIALS_PATH):
        return False
    try:
        st.session_state.drive_service = get_drive_service()
        return True
    except Exception:
        return False


def main():
    st.set_page_config(page_title="Google Drive File Copy", page_icon="📁", layout="centered")
    st.title("Google Drive File Copy")
    st.caption("Copy selected files from one folder to another. Browse and select files, or type their names.")

    init_session_state()

    # Auth step
    if not ensure_authenticated():
        st.info(
            f"**Connect Google Drive**\n\n"
            f"1. Add `{CREDENTIALS_PATH}` to this folder (download from Google Cloud Console).\n"
            f"2. Click **Connect Google Drive** below and sign in in the browser.\n"
            f"3. After authorizing, return here and refresh the app."
        )
        if st.button("Connect Google Drive"):
            try:
                st.session_state.drive_service = get_drive_service()
                st.success("Connected. Refreshing...")
                st.rerun()
            except FileNotFoundError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Authentication failed: {e}")
        return

    service = st.session_state.drive_service

    try:
        folder_paths = build_folder_paths(service)
    except Exception as e:
        st.error(f"Failed to load folder structure: {e}")
        return

    if not folder_paths:
        st.warning("No folders found in your Drive.")
        return

    # Path labels (e.g. "My Drive (root)", "My Drive (root) / card2 / subfolder") -> folder id
    folder_names = [p[0] for p in folder_paths]
    folder_label_to_id = {p[0]: p[1] for p in folder_paths}

    st.caption("Select a folder by its full path (expand the dropdown to see the full structure).")
    # Source folder
    source_label = "Source folder"
    source_index = 0
    if st.session_state.source_folder_id:
        for i, lab in enumerate(folder_names):
            if folder_label_to_id[lab] == st.session_state.source_folder_id:
                source_index = i
                break
    source_name = st.selectbox(
        source_label,
        options=folder_names,
        index=min(source_index, len(folder_names) - 1),
        key="source_select",
    )
    source_folder_id = folder_label_to_id[source_name]
    st.session_state.source_folder_id = source_folder_id
    st.caption(f"Listing files in: **{source_name}**")

    # Load files in source folder for browse/select (cached by folder id so list always matches selection)
    if st.session_state.source_files_cache_id != source_folder_id:
        try:
            st.session_state.source_files_cache = list_files_in_folder(service, source_folder_id)
            st.session_state.source_files_cache_id = source_folder_id
        except Exception:
            st.session_state.source_files_cache = []
            st.session_state.source_files_cache_id = source_folder_id
    source_files = st.session_state.source_files_cache or []

    # Build unique option labels (so duplicate names like two "photo.jpg" both appear)
    # and map option -> (file_id, file_name) for copy
    name_count = {}
    option_to_file = {}
    option_labels = []
    for f in source_files:
        name = f["name"]
        fid, fname = f["id"], f["name"]
        name_count[name] = name_count.get(name, 0) + 1
        if name_count[name] == 1:
            label = name
        else:
            label = f"{name}  ({name_count[name]})"
        option_labels.append(label)
        option_to_file[label] = (fid, fname)
    option_labels.sort(key=str.lower)

    # How to choose files: browse/select or type names
    st.subheader("Choose files to copy")
    col1, col2 = st.columns([1, 1])
    with col1:
        use_browse = st.checkbox("Browse and select from folder (recommended)", value=True, key="use_browse")
    with col2:
        if st.button("Refresh file list", help="Reload the list to include newly added files"):
            st.session_state.source_files_cache_id = None
            st.rerun()
    if use_browse:
        if not option_labels:
            st.info("No files in this folder, or load failed. Click **Refresh file list** or type names below.")
        else:
            total_loaded = len(option_labels)
            st.caption(f"Loaded **{total_loaded}** file(s) from **{source_name}**. Use **Refresh file list** to reload.")
            filter_text = st.text_input(
                "Filter by name (type to narrow the list)",
                key="file_filter",
                placeholder="e.g. 7B1A or .JPG",
                help="Only files whose name contains this text (any case) will appear in the dropdown.",
            )
            if filter_text and filter_text.strip():
                subset = [o for o in option_labels if filter_text.strip().lower() in o.lower()]
                st.caption(f"**{len(subset)}** file(s) match your filter.")
            else:
                subset = option_labels
            selected_options = st.multiselect(
                "Select files to copy",
                options=subset,
                default=None,
                key="browse_selected",
                help="Select one or more files. Use the filter above to narrow the list.",
            )
    else:
        selected_options = []

    # For copy: matched list from browse selection (using option_to_file) or from typed names
    browse_matched = [option_to_file[opt] for opt in selected_options] if selected_options else []

    # Preview: latest selected file (last in selection when using browse)
    latest_for_preview = browse_matched[-1] if browse_matched else None
    if latest_for_preview:
        prev_file_id, prev_file_name = latest_for_preview
        st.subheader("Preview: latest selected file")
        try:
            meta = get_file_metadata(service, prev_file_id)
            mime = (meta.get("mimeType") or "").lower()
            st.caption(f"**{prev_file_name}**")
            if mime.startswith("image/"):
                content = get_file_content(service, prev_file_id)
                if content:
                    st.image(io.BytesIO(content), use_container_width=True)
                else:
                    st.caption("Could not load image preview.")
            elif mime == "application/pdf":
                content = get_file_content(service, prev_file_id)
                if content:
                    b64 = base64.b64encode(content).decode()
                    pdf_iframe = f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="500" type="application/pdf"></iframe>'
                    components.html(pdf_iframe, height=520)
                    st.caption("If the PDF does not appear above, use the link below.")
                else:
                    st.caption("Could not load PDF in-app.")
                st.link_button("Open in Google Drive", f"https://drive.google.com/file/d/{prev_file_id}/preview", type="secondary")
            else:
                view_url = f"https://drive.google.com/file/d/{prev_file_id}/view"
                st.link_button("Open in Google Drive", view_url, type="secondary")
        except Exception as e:
            st.caption(f"Preview unavailable: {e}")
        st.divider()

    file_names_csv = st.text_area(
        "Or type file names (comma-separated)",
        placeholder="e.g. report.pdf, 7B1A0431.JPG",
        height=80,
        key="file_names_csv",
        help="Use this if you prefer typing names, or if the file list above didn’t load.",
    )

    # Destination folder
    dest_label = "Destination folder"
    dest_index = 0
    if st.session_state.dest_folder_id:
        for i, lab in enumerate(folder_names):
            if folder_label_to_id[lab] == st.session_state.dest_folder_id:
                dest_index = i
                break
    dest_name = st.selectbox(
        dest_label,
        options=folder_names,
        index=min(dest_index, len(folder_names) - 1),
        key="dest_select",
    )
    dest_folder_id = folder_label_to_id[dest_name]
    st.session_state.dest_folder_id = dest_folder_id

    if source_folder_id == dest_folder_id:
        st.warning("Source and destination are the same folder. Copies will appear in the same folder.")

    # Copy button
    if st.button("Copy files"):
        # Prefer browse selection; fall back to typed names
        if browse_matched:
            matched = browse_matched
            not_found = []
        else:
            names_raw = [n.strip() for n in file_names_csv.split(",") if n.strip()]
            if not names_raw:
                st.warning("Select at least one file from the list above, or enter file names (comma-separated).")
                return
            matched, not_found = resolve_names_to_file_ids(service, source_folder_id, names_raw)
            if not matched:
                st.warning("No files matched in the source folder. Check the names and try again.")
                if not_found:
                    st.write("Not found:", ", ".join(not_found))
                return
            if not_found:
                st.warning("Some names were not found in the source folder: **" + ", ".join(not_found) + "**")

        progress = st.progress(0.0, text="Copying...")
        total = len(matched)
        success = 0
        errors = []
        for i, (file_id, file_name) in enumerate(matched):
            try:
                copy_file_to_folder(service, file_id, file_name, dest_folder_id)
                success += 1
            except Exception as e:
                errors.append(f"{file_name}: {e}")
            progress.progress((i + 1) / total, text=f"Copying {i + 1}/{total}...")
        progress.progress(1.0, text="Done.")

        st.success(f"Copied **{success}** file(s) to **{dest_name}**.")
        if errors:
            st.error("Errors:\n" + "\n".join(errors))

    st.divider()
    st.caption("Uses Google Drive API. Source files are unchanged; copies are created in the destination folder.")


if __name__ == "__main__":
    main()
