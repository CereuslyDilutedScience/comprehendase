# debug_tools.py
# A clean, isolated debug collector that stays silent unless activated.

class DebugCollector:
    """
    A structured container for collecting debug information across the pipeline.
    Nothing here performs any logic unless the main code explicitly calls it.
    """

    def __init__(self):
        # High-level numeric summaries
        self.counts = {
            "pages": None,
            "words": None,
            "phrases": None,
            "definitions": None,
        }

        # Representative samples (not full dumps)
        self.samples = {
            "words": [],
            "phrases": [],
            "boxes": [],
            "definitions": [],
        }

        # Flow checkpoints (simple breadcrumbs)
        self.flow = []

        # Anomaly summaries + small samples
        self.anomalies = {
            "duplicate_coordinates": [],
            "duplicate_text_spans": [],
            "overlapping_boxes": [],
            "empty_phrases": [],
        }

        # Whether debug output is active
        self.enabled = False

    def enable(self):
        """Turn on debug collection."""
        self.enabled = True

    def disable(self):
        """Turn off debug collection."""
        self.enabled = False

    def add_flow(self, message: str):
        """Record a pipeline checkpoint."""
        if self.enabled:
            self.flow.append(message)

    def set_count(self, key: str, value: int):
        """Set a numeric count (pages, words, phrases, definitions)."""
        if self.enabled and key in self.counts:
            self.counts[key] = value

    def add_sample(self, key: str, item, limit=10):
        """
        Add a sample object to a category (words, phrases, boxes, definitions).
        Only keeps up to `limit` items.
        """
        if self.enabled and key in self.samples:
            if len(self.samples[key]) < limit:
                self.samples[key].append(item)

    def add_anomaly(self, key: str, item, limit=10):
        """
        Add an anomaly sample (duplicates, overlaps, empties).
        Only keeps up to `limit` items.
        """
        if self.enabled and key in self.anomalies:
            if len(self.anomalies[key]) < limit:
                self.anomalies[key].append(item)

    def emit(self):
        """
        Produce a single consolidated debug report as a formatted string.
        The main pipeline can print this once per request.
        """
        if not self.enabled:
            return ""

        report = []
        report.append("=== DEBUG REPORT START ===")

        # Counts
        report.append("\nCOUNTS:")
        for k, v in self.counts.items():
            report.append(f"  {k}: {v}")

        # Flow checkpoints
        report.append("\nFLOW CHECKPOINTS:")
        for step in self.flow:
            report.append(f"  - {step}")

        # Samples
        report.append("\nSAMPLES:")
        for k, items in self.samples.items():
            report.append(f"  {k} (sample of {len(items)}):")
            for item in items:
                report.append(f"    {item}")

        # Anomalies
        report.append("\nANOMALIES:")
        for k, items in self.anomalies.items():
            report.append(f"  {k}: {len(items)} (sample shown)")
            for item in items:
                report.append(f"    {item}")

        report.append("=== DEBUG REPORT END ===")

        return "\n".join(report)


# A single global collector instance that the pipeline can import.
DEBUG = DebugCollector()
