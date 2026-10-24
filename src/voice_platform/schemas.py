from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class ProjectInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="通用", max_length=80)
    description: str = Field(default="", max_length=2000)

class VoiceInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    languages: list[str] = Field(default_factory=lambda: ["zh"], max_length=30)
    traits: str = Field(default="", max_length=1000)
    engine: str | None = None
    style: str = Field(default="", max_length=1000)
    seed: int = Field(default=42, ge=0, le=2147483647)
    engine_options: dict = Field(default_factory=dict)
    reference_id: str | None = None
    reference_ids: list[str] = Field(default_factory=list, max_length=40)
    reference_scenarios: dict[str, str] = Field(default_factory=dict)
    reference_confirmed: bool = False
    sample_result_id: str | None = None
    project_id: str | None = None
    status: Literal["draft", "active", "archived"] = "draft"

class GenerationInput(StrictModel):
    text: str = Field(min_length=1, max_length=60000)
    title: str = Field(default="未命名配音", min_length=1, max_length=120)
    project_id: str | None = None
    voice_id: str | None = None
    reference_id: str | None = None
    clone_mode: Literal["reference", "hifi"] = "reference"
    engine: str | None = None
    style: str = Field(default="", max_length=1000)
    language: str = Field(default="auto", max_length=30)
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    candidates: int = Field(default=1, ge=1, le=5)
    streaming: bool = False
    engine_options: dict = Field(default_factory=dict)
    max_retries: int = Field(default=1, ge=0, le=3)

class BatchInput(StrictModel):
    items: list[GenerationInput] = Field(min_length=1, max_length=200)

class SettingsInput(StrictModel):
    idle_unload_seconds: int = Field(ge=30, le=86400)
    segment_chars: int = Field(ge=40, le=500)
    segment_pause_ms: int = Field(ge=0, le=2000)
    max_pending_jobs: int = Field(ge=1, le=2000)
    task_archive_after_days: int | None = Field(default=None, ge=0, le=3650)

class ArchiveJobsInput(StrictModel):
    job_ids: list[str] = Field(min_length=1, max_length=200)

class SaveClipsInput(StrictModel):
    reference_ids: list[str] = Field(min_length=1, max_length=40)

class ReferenceMetadataInput(StrictModel):
    name: str = Field(default='', max_length=100)
    scenario: str = Field(default='', max_length=80)
    notes: str = Field(default='', max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator('tags')
    @classmethod
    def clean_tags(cls, value):
        tags = list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))
        if any(len(tag)>80 for tag in tags):raise ValueError('单个参考标签不能超过 80 字')
        return tags

class ProcessingInput(StrictModel):
    recording_id: str
    operations: list[Literal['remove_music','denoise','separate']] = Field(default_factory=lambda:['remove_music','denoise','separate'],min_length=1,max_length=3)
    analyze_outputs: bool = True

    @model_validator(mode='after')
    def unique_operations(self):
        if len(set(self.operations))!=len(self.operations):raise ValueError('同一次处理不能重复执行同一操作')
        return self

class ResultRecordingInput(StrictModel):
    result_id: str

class OutputRecordingInput(StrictModel):
    output_id: str

class ReferenceVoiceInput(StrictModel):
    reference_id: str
    name: str = Field(default='',max_length=100)
    voice_id: str | None = None
    scenario: str = Field(default='',max_length=80)

    @model_validator(mode='after')
    def target(self):
        if not self.name and not self.voice_id:raise ValueError('请填写人物名称或选择已有的人物')
        return self

class TranscriptInput(StrictModel):
    text: str = Field(max_length=6000)
    confirmed: bool = False

class CompareReferencesInput(StrictModel):
    voice_id: str
    reference_ids: list[str] = Field(min_length=2, max_length=8)
    text: str = Field(default="夜色渐深，城市终于安静下来。故事，就从这里开始。", min_length=5, max_length=300)
    seeds: list[int] = Field(default_factory=lambda: [42, 84], min_length=2, max_length=3)
    clone_mode: Literal["reference", "hifi"] = "reference"

class ReviewInput(StrictModel):
    status: Literal["approved", "rejected", "pending"]
    listened: bool = False
    reviewer: str = Field(default="本机用户", min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def require_listening(self):
        if self.status == "approved" and not self.listened:
            raise ValueError("请实际试听后明确确认；未经试听不能批准正式资产")
        return self

class ExportInput(StrictModel):
    result_ids: list[str] = Field(min_length=1, max_length=500)
    adapter: str = "standard"
    format: Literal["wav", "mp3", "flac", "ogg"] = "wav"
    sample_rate: int = Field(default=48000, ge=8000, le=96000)
    channels: Literal[1, 2] = 1
    normalize: bool = False
    trim_silence: bool = False
    naming: str = Field(default="{title}_{candidate}_{id}", max_length=150)
    draft: bool = False
    subtitles: bool = True


class LongformImportRetry(StrictModel):
    encoding: Literal['auto','utf-8-sig','utf-16','utf-16-le','utf-16-be','gb18030','gbk','gb2312'] = 'auto'

class LongformAction(StrictModel):
    chapter_no: int | None = Field(default=None,ge=1)

class RegenerationInput(StrictModel):
    reference_id: str | None = None
    style: str | None = Field(default=None, max_length=1000)
    clone_mode: Literal['reference','hifi'] | None = None
    seed: int | None = Field(default=None, ge=0, le=2147483646)

class LongformRegenerationInput(RegenerationInput):
    use_book_defaults: bool = False
    start: bool = False

class UseAttemptInput(StrictModel):
    attempt: int = Field(ge=1)

class LongformExportInput(StrictModel):
    chapter_no: int | None = Field(default=None,ge=1)
    mode: Literal['chapters','book'] = 'chapters'
    format: Literal['wav','mp3','flac','ogg'] = 'wav'
    draft: bool = False


class AssetItem(StrictModel):
    kind: str = Field(min_length=1,max_length=40)
    id: str = Field(min_length=1,max_length=200)

class AssetBatch(StrictModel):
    items: list[AssetItem] = Field(min_length=1,max_length=200)
    cascade: bool = True

class ReviewBatch(ReviewInput):
    result_ids: list[str] = Field(min_length=1,max_length=200)
