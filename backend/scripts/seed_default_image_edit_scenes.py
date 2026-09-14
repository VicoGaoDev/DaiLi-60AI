from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.services.external_api_config_service import (
    DEFAULT_SCENE_DEFINITIONS,
    SCENE_TYPE_IMAGE_EDIT,
    _ensure_scene_bindings,
)


def main() -> None:
    target_keys = [
        item["scene_key"]
        for item in DEFAULT_SCENE_DEFINITIONS
        if item["scene_type"] == SCENE_TYPE_IMAGE_EDIT
    ]

    db = SessionLocal()
    try:
        before_keys = {
            row.scene_key
            for row in db.query(ExternalApiSceneBinding)
            .filter(ExternalApiSceneBinding.scene_key.in_(target_keys))
            .all()
        }

        _ensure_scene_bindings(db)

        after_rows = (
            db.query(ExternalApiSceneBinding)
            .filter(ExternalApiSceneBinding.scene_key.in_(target_keys))
            .order_by(ExternalApiSceneBinding.sort_order.asc(), ExternalApiSceneBinding.id.asc())
            .all()
        )
        after_keys = {row.scene_key for row in after_rows}
        added_keys = sorted(after_keys - before_keys)

        print(f"image_edit scenes present: {len(after_rows)}/{len(target_keys)}")
        if added_keys:
            print("inserted:")
            for key in added_keys:
                print(f"  - {key}")
        else:
            print("no new rows inserted")

        print("current rows:")
        for row in after_rows:
            print(
                f"  - {row.scene_key} | type={row.scene_type} | "
                f"api_config_id={row.api_config_id} | credit_cost={row.credit_cost}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
