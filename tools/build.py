"""Build the local diagnostic archive using only the Python standard library."""
from hashlib import sha256
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZipInfo, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
FOLDER = "SpokenCommunity_ukrainian-diagnostic"
FILES = ("Lore.lua", FOLDER + ".toc")
METADATA = {
    "Interface": "16001",
    "Title": "Spoken Ukrainian Diagnostic",
    "Version": "0.1.0",
    "Dependencies": "Spoken, Spoken_Places",
    "X-SpokenPlaces-Language": "ukUA",
    "X-SpokenPlaces-Lore": "1",
    "X-Spoken-LanguageName": "Ukrainian",
    "X-Spoken-LanguageNative": "Українська",
}


def safe_path(name):
    parts = PurePosixPath(name).parts
    if (not name or "\\" in name or ":" in name or name.startswith("/")
            or any(p in ("", ".", "..") for p in name.split("/"))
            or not parts or parts[0] != FOLDER):
        raise ValueError(f"Invalid archive path: {name!r}")
    return name


def read_toc(source):
    metadata, files = {}, []
    for line in (source / (FOLDER + ".toc")).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            key, value = line[3:].split(":", 1)
            if key in metadata:
                raise ValueError(f"Duplicate TOC key: {key}")
            metadata[key] = value.strip()
        elif line.strip() and not line.startswith("#"):
            files.append(line.strip())
    return metadata, files


def build(output=None, source=None):
    source = Path(source) if source else ROOT / "addons" / FOLDER
    if source.is_symlink() or source.name != FOLDER:
        raise ValueError("Expected a real diagnostic addon folder")
    entries = list(source.iterdir())
    if {p.name for p in entries} != set(FILES):
        raise ValueError("Addon must contain exactly its TOC and Lore.lua")
    if any(p.is_symlink() or not p.is_file() for p in entries):
        raise ValueError("Addon entries must be regular files, not links")
    metadata, files = read_toc(source)
    if metadata != METADATA or files != ["Lore.lua"]:
        raise ValueError("Unexpected diagnostic TOC metadata or load order")
    output = Path(output) if output else ROOT / "dist" / (FOLDER + ".zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stored bytes avoid compressor-version differences between Python installations.
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name in sorted(FILES):
            entry = ZipInfo(safe_path(FOLDER + "/" + name), (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, (source / name).read_bytes())
    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    return output, digest, output.stat().st_size


if __name__ == "__main__":
    path, digest, size = build()
    print(f"Archive: {path}\nSHA-256: {digest}\nSize: {size} bytes")
