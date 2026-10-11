"""Copy installed dependency license files into the portable distribution."""

from importlib.metadata import distributions
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent.parent
target = root / "dist/VoiceFX/licenses"
target.mkdir(parents=True, exist_ok=True)
for dist in distributions():
    name = dist.metadata.get("Name", "package")
    for entry in dist.files or []:
        text = str(entry).lower()
        if "license" in text or "copying" in text or "notice" in text:
            source = Path(dist.locate_file(entry))
            if source.is_file() and source.suffix.lower() not in (
                ".py",
                ".pyc",
                ".pyd",
            ):
                relative = Path(
                    *[p for p in Path(str(entry)).parts if p not in (".", "..")]
                )
                dest = target / name / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
shutil.copy2(root / "LICENSE", target / "VoiceFX-MIT.txt")
shutil.copy2(root / "THIRD-PARTY.md", target / "THIRD-PARTY.md")
shutil.copy2(root / "THIRD-PARTY.md", root / "dist/VoiceFX/_internal/THIRD-PARTY.md")
shutil.copy2(root / "README.md", root / "dist/VoiceFX/README.md")
shutil.copytree(root / "licenses", target / "Qt", dirs_exist_ok=True)
print("Dependency notices copied into the portable app.")
