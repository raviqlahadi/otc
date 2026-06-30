import json
from pathlib import Path

from models import BKTParams, KCConfig

DEFAULT_RESOURCE_PATH = Path(__file__).parent.parent / "resources" / "09_model_parameters_REVISED_affective_context.json"


class BKTConfigLoader:
    @staticmethod
    def load_from_json(path: Path = DEFAULT_RESOURCE_PATH) -> dict[str, BKTParams]:
        """Load per-KC BKT params from JSON. Returns dict mapping kc_id -> BKTParams."""
        if not path.exists():
            raise FileNotFoundError(f"BKT config not found: {path}")
        data = json.loads(path.read_text())
        params = {}
        for kc_id, cfg in data["bkt_parameters"].items():
            p = BKTParams(
                p_l0=cfg["p_L0"],
                p_guess=cfg["p_guess"],
                p_slip=cfg["p_slip"],
                p_transit=cfg["p_transition"],
            )
            BKTConfigLoader._validate(p, kc_id)
            params[kc_id] = p
        return params

    @staticmethod
    def load_kc_configs(path: Path = DEFAULT_RESOURCE_PATH) -> dict[str, KCConfig]:
        """Load full KC configs including thresholds."""
        if not path.exists():
            raise FileNotFoundError(f"BKT config not found: {path}")
        data = json.loads(path.read_text())
        configs = {}
        for kc_id, cfg in data["bkt_parameters"].items():
            kc = KCConfig(
                kc_id=kc_id,
                p_l0=cfg["p_L0"],
                p_guess=cfg["p_guess"],
                p_slip=cfg["p_slip"],
                p_transit=cfg["p_transition"],
                mastery_threshold=cfg.get("mastery_threshold", 0.8),
                needs_review_threshold=cfg.get("needs_review_threshold", 0.5),
            )
            BKTConfigLoader._validate_kc(kc)
            configs[kc_id] = kc
        return configs

    @staticmethod
    def _validate(p: BKTParams, kc_id: str) -> None:
        for name, val in [("p_l0", p.p_l0), ("p_guess", p.p_guess), ("p_slip", p.p_slip), ("p_transit", p.p_transit)]:
            assert 0.0 <= val <= 1.0, f"{kc_id}.{name}={val} not in [0,1]"

    @staticmethod
    def _validate_kc(kc: KCConfig) -> None:
        for name, val in [("p_l0", kc.p_l0), ("p_guess", kc.p_guess), ("p_slip", kc.p_slip), ("p_transit", kc.p_transit)]:
            assert 0.0 <= val <= 1.0, f"{kc.kc_id}.{name}={val} not in [0,1]"
