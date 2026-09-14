import re
import difflib
from typing import Tuple


class VesselNameNormalizer:
    @staticmethod
    def normalize(name: str | None) -> str:
        """
        Normalises vessel names by removing punctuation, trailing characters,
        extra whitespace, and standardizing casing while preserving the underlying name.
        Handles MSC AURORA / MSC AURORA. / MSC-AURORA / SYNTHETIC- HORIZON 12 -> SYNTHETIC HORIZON 12.
        """
        if not name:
            return ""
        
        # Uppercase
        s = name.strip().upper()
        
        # Replace punctuation, hyphens, periods, underscores with space
        s = re.sub(r"[^A-Z0-9]+", " ", s)
        
        # Collapse multiple spaces into single space
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @classmethod
    def similarity(cls, name1: str | None, name2: str | None) -> Tuple[float, str]:
        """
        Calculates similarity between two vessel names.
        Returns (similarity_score, explanation).
        """
        if not name1 or not name2:
            return 0.0, "One or both names are empty"

        raw1 = name1.strip().upper()
        raw2 = name2.strip().upper()

        if raw1 == raw2:
            return 1.0, f"Exact verbatim match ('{name1}')"

        norm1 = cls.normalize(name1)
        norm2 = cls.normalize(name2)

        if norm1 == norm2:
            return 0.99, f"Exact match after normalisation ('{norm1}')"

        ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()
        if ratio >= 0.90:
            return round(ratio, 4), f"Close normalisation match ({norm1} vs {norm2}, ratio: {ratio:.2f})"
        
        return round(ratio, 4), f"Probabilistic string similarity ratio: {ratio:.2f}"
