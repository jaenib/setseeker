from __future__ import annotations

import os
import shutil
import subprocess
import time
import unicodedata
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol, Sequence

from reciprocity import ReciprocityAuditError, ReciprocityConfig, SlskdApiClient


def _dict_get_ci(data: dict, *names: str):
    if not isinstance(data, dict):
        return None
    lowered = {str(key).lower(): value for key, value in data.items()}
    for name in names:
        key = name.lower()
        if key in lowered:
            return lowered[key]
    return None


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    collapsed = []
    for char in ascii_text.lower():
        collapsed.append(char if char.isalnum() else " ")
    return " ".join("".join(collapsed).split())


def _tokens(value: str) -> list[str]:
    return [token for token in _normalize_text(value).split() if len(token) > 1]


def _guess_transfer_state(transfer: dict) -> str:
    state = _dict_get_ci(transfer, "stateDescription", "state")
    if state is None:
        return ""
    return str(state)


def _is_transfer_succeeded(transfer: dict) -> bool:
    return "completed" in _guess_transfer_state(transfer).lower() and "succeeded" in _guess_transfer_state(transfer).lower()


def _is_transfer_terminal(transfer: dict) -> bool:
    return "completed" in _guess_transfer_state(transfer).lower()


def _url_hostname(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").strip().lower()


def _is_local_backend(url: str) -> bool:
    return _url_hostname(url) in {"localhost", "127.0.0.1", "::1"}


def remote_to_local_relative_filename(remote_filename: str) -> Path:
    localized = remote_filename.replace("\\", "/")
    parts = [part for part in localized.split("/") if part]
    if not parts:
        raise ValueError("remote filename is empty")
    if len(parts) == 1:
        safe = _replace_invalid_filename_chars(parts[0])
        return Path(safe)
    parent = _replace_invalid_filename_chars(parts[-2])
    leaf = _replace_invalid_filename_chars(parts[-1])
    return Path(parent) / leaf


def _replace_invalid_filename_chars(value: str) -> str:
    invalid = set('/\\?%*:|"<>')
    return "".join("_" if char in invalid else char for char in value)


@dataclass(frozen=True)
class TrackQuery:
    artist: str
    title: str
    format: str
    min_bitrate: int = 0
    source_file: str = ""
    source_line: int = 0
    raw_line: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title} [{self.format}]"

    @property
    def search_text(self) -> str:
        return f"{self.artist} {self.title}".strip()


@dataclass
class TrackDownloadResult:
    query: TrackQuery
    status: str
    detail: str
    remote_username: Optional[str] = None
    remote_filename: Optional[str] = None
    local_path: Optional[Path] = None
    size_bytes: int = 0


@dataclass
class DownloadRunSummary:
    backend: str
    results: list[TrackDownloadResult] = field(default_factory=list)
    mirrored_count: int = 0
    mirror_failures: int = 0

    @property
    def requested_count(self) -> int:
        return len(self.results)

    @property
    def succeeded_count(self) -> int:
        return sum(1 for result in self.results if result.status == "downloaded")

    @property
    def missed_count(self) -> int:
        return sum(1 for result in self.results if result.status == "missed")

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.results if result.status == "failed")

    @property
    def total_downloaded_bytes(self) -> int:
        return sum(result.size_bytes for result in self.results if result.status == "downloaded")


class DownloadBackend(Protocol):
    name: str

    def download_queries(self, queries: Sequence[TrackQuery]) -> DownloadRunSummary:
        raise NotImplementedError


class SldlDownloadBackend:
    name = "legacy-sldl"

    def __init__(
        self,
        executable: str,
        queryfile_path: Path,
        username: str,
        password: str,
        output_dir: Path,
        env: dict[str, str],
    ):
        self.executable = executable
        self.queryfile_path = Path(queryfile_path)
        self.username = username
        self.password = password
        self.output_dir = output_dir
        self.env = env

    def download_queries(self, queries: Sequence[TrackQuery]) -> DownloadRunSummary:
        del queries
        command = [
            "dotnet",
            self.executable,
            str(self.queryfile_path),
            "--user",
            self.username,
            "--pass",
            self.password,
            "--input-type=list",
            "--no-modify-share-count",
            "--path",
            str(self.output_dir),
        ]
        subprocess.run(command, env=self.env, check=True)
        return DownloadRunSummary(backend=self.name)


class SlskdDownloadBackend:
    name = "slskd"

    def __init__(
        self,
        config: ReciprocityConfig,
        output_dir: Path,
        echo: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.echo = echo
        self.sleep = sleep
        self.client = SlskdApiClient(config.slskd)
        self.options = self.client.get_options()
        self.base_url = self.config.slskd.url
        self.local_download_root = self._resolve_local_download_root()

    def download_queries(self, queries: Sequence[TrackQuery]) -> DownloadRunSummary:
        summary = DownloadRunSummary(backend=self.name)

        for index, query in enumerate(queries, start=1):
            self.echo(f"[{index}/{len(queries)}] Searching via slskd: {query.display_name}")
            try:
                result = self._download_single_query(query)
            except ReciprocityAuditError as exc:
                result = TrackDownloadResult(query=query, status="failed", detail=str(exc))
            except Exception as exc:  # pragma: no cover - defensive boundary for live API runs
                result = TrackDownloadResult(query=query, status="failed", detail=str(exc))
            summary.results.append(result)
            if result.status == "downloaded" and result.local_path is not None:
                summary.mirrored_count += 1
            if result.status == "downloaded" and result.local_path is None:
                summary.mirror_failures += 1
            self.echo(self._format_result_line(result))

        return summary

    def _download_single_query(self, query: TrackQuery) -> TrackDownloadResult:
        search_id = uuid.uuid4()
        self.client.create_search(
            search_id=search_id,
            search_text=query.search_text,
            search_timeout=self.config.slskd.search_timeout_seconds,
            response_limit=self.config.slskd.response_limit,
            file_limit=self.config.slskd.file_limit,
        )

        try:
            search = self._wait_for_search(search_id)
            responses = self.client.get_search_responses(search_id)
        finally:
            self.client.delete_search(search_id)

        candidate = self._pick_candidate(query, responses)
        if candidate is None:
            return TrackDownloadResult(query=query, status="missed", detail="no acceptable search result")

        enqueue_response = self.client.enqueue_download(
            username=candidate["username"],
            files=[{"filename": candidate["filename"], "size": candidate["size"]}],
        )
        enqueued = _dict_get_ci(enqueue_response, "enqueued")
        enqueued_transfer = enqueued[0] if isinstance(enqueued, list) and enqueued else None
        transfer = self._wait_for_transfer(candidate, enqueued_transfer)

        if not _is_transfer_succeeded(transfer):
            return TrackDownloadResult(
                query=query,
                status="failed",
                detail=_guess_transfer_state(transfer) or "transfer did not succeed",
                remote_username=candidate["username"],
                remote_filename=candidate["filename"],
                size_bytes=_safe_int(_dict_get_ci(transfer, "size"), candidate["size"]),
            )

        local_path = self._mirror_to_spoils(candidate["filename"])
        detail = "downloaded to slskd and mirrored into spoils/" if local_path else "downloaded in slskd downloads directory only"
        return TrackDownloadResult(
            query=query,
            status="downloaded",
            detail=detail,
            remote_username=candidate["username"],
            remote_filename=candidate["filename"],
            local_path=local_path,
            size_bytes=_safe_int(_dict_get_ci(transfer, "size"), candidate["size"]),
        )

    def _wait_for_search(self, search_id):
        deadline = time.monotonic() + max(self.config.slskd.search_timeout_seconds + 10, 15)
        while time.monotonic() < deadline:
            search = self.client.get_search(search_id, include_responses=False)
            if self._search_complete(search):
                return search
            self.sleep(self.config.slskd.poll_interval_seconds)
        raise ReciprocityAuditError(f"slskd search {search_id} did not complete in time")

    def _wait_for_transfer(self, candidate: dict, enqueued_transfer: Optional[dict]):
        deadline = time.monotonic() + max(self.config.slskd.transfer_timeout_seconds, 30)
        transfer_id = str(_dict_get_ci(enqueued_transfer or {}, "id") or "")
        while time.monotonic() < deadline:
            transfers = self.client.list_downloads(username=candidate["username"], include_removed=True)
            transfer = self._match_transfer(transfers, transfer_id=transfer_id, remote_filename=candidate["filename"])
            if transfer is not None and _is_transfer_terminal(transfer):
                return transfer
            self.sleep(self.config.slskd.poll_interval_seconds)
        raise ReciprocityAuditError(f"slskd transfer for {candidate['filename']} did not complete in time")

    def _pick_candidate(self, query: TrackQuery, responses: Sequence[dict]) -> Optional[dict]:
        scored = []
        for response in responses or []:
            username = str(_dict_get_ci(response, "username") or "").strip()
            queue_length = _safe_int(_dict_get_ci(response, "queueLength"), 0)
            upload_speed = _safe_int(_dict_get_ci(response, "uploadSpeed"), 0)
            has_free_slot = bool(_dict_get_ci(response, "hasFreeUploadSlot"))
            files = list(_dict_get_ci(response, "files") or [])
            for file_info in files:
                score = self._score_file(query, response, file_info)
                if score is None:
                    continue
                scored.append(
                    {
                        "score": score,
                        "username": username,
                        "filename": str(_dict_get_ci(file_info, "filename") or ""),
                        "size": _safe_int(_dict_get_ci(file_info, "size"), 0),
                        "queue_length": queue_length,
                        "upload_speed": upload_speed,
                        "has_free_slot": has_free_slot,
                    }
                )

        if not scored:
            return None

        scored.sort(
            key=lambda item: (
                item["score"],
                item["has_free_slot"],
                -item["queue_length"],
                item["upload_speed"],
                -item["size"],
            ),
            reverse=True,
        )
        return scored[0]

    def _score_file(self, query: TrackQuery, response: dict, file_info: dict) -> Optional[float]:
        filename = str(_dict_get_ci(file_info, "filename") or "")
        extension = str(_dict_get_ci(file_info, "extension") or Path(filename).suffix.lstrip(".")).lower()
        if extension != query.format:
            return None

        bit_rate = _safe_int(_dict_get_ci(file_info, "bitRate"), 0)
        if query.format == "mp3" and bit_rate < query.min_bitrate:
            return None

        normalized_filename = _normalize_text(filename)
        artist_tokens = _tokens(query.artist)
        title_tokens = _tokens(query.title)
        artist_hits = sum(1 for token in artist_tokens if token in normalized_filename)
        title_hits = sum(1 for token in title_tokens if token in normalized_filename)

        if artist_tokens and artist_hits == 0:
            return None
        if title_tokens and title_hits == 0:
            return None

        total_possible = max(len(artist_tokens) + len(title_tokens), 1)
        token_score = (artist_hits + title_hits) / total_possible

        exact_phrase = _normalize_text(f"{query.artist} {query.title}")
        score = 100 * token_score
        if exact_phrase and exact_phrase in normalized_filename:
            score += 40

        if query.format == "flac":
            score += 25
        else:
            score += min(max(bit_rate - query.min_bitrate, 0), 64) / 4
            if _dict_get_ci(file_info, "isVariableBitRate") is False:
                score += 3

        if bool(_dict_get_ci(response, "hasFreeUploadSlot")):
            score += 8

        queue_length = _safe_int(_dict_get_ci(response, "queueLength"), 0)
        upload_speed = _safe_int(_dict_get_ci(response, "uploadSpeed"), 0)
        score -= min(queue_length, 2000) / 100
        score += min(upload_speed, 2_000_000) / 250_000

        return score

    def _search_complete(self, search: dict) -> bool:
        explicit = _dict_get_ci(search, "isComplete")
        if explicit is not None:
            return bool(explicit)
        ended_at = _dict_get_ci(search, "endedAt")
        if ended_at:
            return True
        state = str(_dict_get_ci(search, "state") or "")
        return "completed" in state.lower()

    def _match_transfer(self, transfers: Sequence[dict], transfer_id: str, remote_filename: str) -> Optional[dict]:
        if transfer_id:
            for transfer in transfers:
                if str(_dict_get_ci(transfer, "id") or "") == transfer_id:
                    return transfer
        for transfer in transfers:
            if str(_dict_get_ci(transfer, "filename") or "") == remote_filename:
                return transfer
        return None

    def _resolve_local_download_root(self) -> Optional[Path]:
        downloads_dir = _dict_get_ci(self.options, "directories")
        if not isinstance(downloads_dir, dict):
            return None
        base = str(_dict_get_ci(downloads_dir, "downloads") or "").strip()
        if not base:
            return None
        if not _is_local_backend(self.base_url):
            return None
        path = Path(base).expanduser()
        return path if path.exists() else None

    def _mirror_to_spoils(self, remote_filename: str) -> Optional[Path]:
        if not self.config.slskd.mirror_downloads_to_spoils:
            return None
        if self.local_download_root is None:
            return None

        source = self.local_download_root / remote_to_local_relative_filename(remote_filename)
        if not source.is_file():
            return None

        destination = self.output_dir / remote_to_local_relative_filename(remote_filename)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if source.resolve() == destination.resolve():
            return destination

        try:
            if destination.exists():
                source_stat = source.stat()
                dest_stat = destination.stat()
                if source_stat.st_size == dest_stat.st_size:
                    return destination
            try:
                if destination.exists():
                    destination.unlink()
                os.link(source, destination)
            except OSError:
                shutil.copy2(source, destination)
            return destination
        except OSError:
            return None

    def _format_result_line(self, result: TrackDownloadResult) -> str:
        if result.status == "downloaded":
            if result.local_path:
                return f"  OK  {result.query.display_name} -> {result.local_path}"
            return f"  OK  {result.query.display_name} -> {result.detail}"
        if result.status == "missed":
            return f"  MISS {result.query.display_name} -> {result.detail}"
        return f"  FAIL {result.query.display_name} -> {result.detail}"
