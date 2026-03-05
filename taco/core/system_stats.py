from datetime import datetime


class SystemStats:
    def __init__(self, system_id: int = -1):
        self.system_id = system_id
        self.report_count = 1
        self.last_report = datetime.now()
        self.expired = False
        self.last_intel_report = ""

    def update(self, intel_report: str | None = None):
        self.last_report = datetime.now()
        self.report_count += 1
        self.expired = False
        if intel_report is not None:
            self.last_intel_report = intel_report
