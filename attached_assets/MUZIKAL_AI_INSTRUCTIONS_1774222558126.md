# 🎵 MUZIKAL — הוראות מלאות לשיפור, תיקון וסידור הפרויקט
> מסמך זה מיועד ל-AI שיטפל בקוד. יש לבצע לפי הסדר. כל סעיף הוא עצמאי ומדויק.

---

## ⚠️ כללי עבודה חובה

- **אל תשכתב קבצים מאפס** אלא אם צוין במפורש.
- **שינויים כירורגיים בלבד** — שנה רק את מה שנדרש.
- **אחרי כל שלב** — הרץ את הטסטים ווודא שאין רגרסיה.
- **לפני כל שינוי ב-schema** — בדוק תלויות בכל הקוד.

---

## 🔴 PHASE 1 — תיקוני קריטי (BUG FIXES)

### 1.1 — תיקון סכמת Jobs חסרה
**קבצים:** `lib/db/src/schema/projects.ts`

הוסף לטבלת `jobs` את העמודות החסרות:
```typescript
startedAt: timestamp("started_at"),
finishedAt: timestamp("finished_at"),
errorCode: varchar("error_code", { length: 100 }),
inputPayload: jsonb("input_payload"),
outputPayload: jsonb("output_payload"),
```
אחרי ההוספה: הרץ `pnpm --filter @workspace/db run push-force`.

---

### 1.2 — תיקון MOCK_MODE — הסרת כשלון שקט
**קבצים:** `artifacts/api-server/src/routes/projects.ts`

**הבעיה:** כאשר `MOCK_MODE=false` ו-Python backend נכשל, הקוד ממשיך בשקט במקום להחזיר שגיאה.

**תיקון:** מצא כל מקום שמטפל ב-fallback ל-mock כאשר Python נכשל:
```typescript
// לפני (שגוי):
} catch (err) {
  // fallback to mock silently
  return generateMockResult();
}

// אחרי (נכון):
} catch (err) {
  if (process.env.MOCK_MODE !== 'true') {
    throw err; // Job fails immediately in production
  }
  logger.warn('[MOCK FALLBACK] Python backend failed, using mock');
  return generateMockResult();
}
```

---

### 1.3 — תיקון WebSocket — reconnection loop
**קבצים:** `artifacts/music-daw/src/hooks/use-job-websocket.ts`

**הבעיה:** כאשר ה-WebSocket נסגר עקב timeout, הקוד מנסה להתחבר מחדש ללא הגבלה.

**תיקון:** הוסף מגבלת ניסיונות וbackoff:
```typescript
const MAX_RETRIES = 5;
const BACKOFF_BASE = 1000; // ms

let retryCount = 0;

function reconnect() {
  if (retryCount >= MAX_RETRIES) {
    console.warn('WebSocket: max retries reached, falling back to polling');
    startPollingFallback();
    return;
  }
  const delay = BACKOFF_BASE * Math.pow(2, retryCount);
  retryCount++;
  setTimeout(connect, delay);
}
```

---

### 1.4 — תיקון Audio Streaming — Range Requests
**קבצים:** `artifacts/api-server/src/routes/projects.ts` — נתיב `/api/projects/:id/audio`

**הבעיה:** ה-endpoint לא מטפל נכון ב-HTTP Range requests — זה שובר playback ב-Safari ו-iOS.

**תיקון:** הוסף טיפול מלא ב-Range headers:
```typescript
const stat = fs.statSync(audioPath);
const fileSize = stat.size;
const range = req.headers.range;

if (range) {
  const parts = range.replace(/bytes=/, '').split('-');
  const start = parseInt(parts[0], 10);
  const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
  const chunkSize = (end - start) + 1;

  res.writeHead(206, {
    'Content-Range': `bytes ${start}-${end}/${fileSize}`,
    'Accept-Ranges': 'bytes',
    'Content-Length': chunkSize,
    'Content-Type': 'audio/mpeg',
  });
  fs.createReadStream(audioPath, { start, end }).pipe(res);
} else {
  res.writeHead(200, {
    'Content-Length': fileSize,
    'Content-Type': 'audio/mpeg',
    'Accept-Ranges': 'bytes',
  });
  fs.createReadStream(audioPath).pipe(res);
}
```

---

### 1.5 — תיקון Python analyzer — חוסר טיפול בשגיאות חלקיות
**קבצים:** `artifacts/music-ai-backend/audio/analyzer.py`

**הבעיה:** אם מודול אחד נכשל (למשל `vocal_analysis`), כל ה-pipeline נכשל.

**תיקון:** עטוף כל שלב בתוך try/except נפרד עם ערך ברירת מחדל:
```python
def _run_step(self, step_name: str, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        self._update_job_progress(step_name, 'completed')
        return result
    except Exception as e:
        logger.error(f"[ANALYZER] Step '{step_name}' failed: {e}")
        self._update_job_progress(step_name, 'failed', str(e))
        return self._default_result(step_name)
```
וודא שיש `_default_result(step_name)` שמחזיר ערכי fallback לכל שלב.

---

## 🟠 PHASE 2 — שיפורי ביצועים

### 2.1 — הוסף Feature Cache לאנליזה
**קבצים:** `packages/audio_core/feature_cache.py` (קיים אך ריק), `artifacts/music-ai-backend/audio/analyzer.py`

**יצור:** מנגנון cache מבוסס checksum:
```python
# feature_cache.py
import hashlib, json, os
from pathlib import Path

CACHE_DIR = Path("/tmp/muzikal_cache")
CACHE_DIR.mkdir(exist_ok=True)

def get_cache_key(audio_path: str, pipeline_version: str) -> str:
    with open(audio_path, 'rb') as f:
        checksum = hashlib.sha256(f.read()).hexdigest()[:16]
    return f"{checksum}_{pipeline_version}"

def load_features(cache_key: str) -> dict | None:
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    return None

def save_features(cache_key: str, features: dict):
    cache_file = CACHE_DIR / f"{cache_key}.json"
    with open(cache_file, 'w') as f:
        json.dump(features, f)
```

**שנה ב-`analyzer.py`:** בדוק cache לפני חישוב מחדש:
```python
cache_key = get_cache_key(audio_path, PIPELINE_VERSION)
cached = load_features(cache_key)
if cached:
    logger.info(f"[CACHE HIT] {cache_key}")
    return cached
```

---

### 2.2 — הורד previewHtml מ-SELECT רגיל
**קבצים:** `lib/db/src/schema/projects.ts`, כל routes שמביאות רשימות

**הוסף ב-schema.ts:**
```typescript
export const projectsTableMeta = {
  id: projectsTable.id,
  name: projectsTable.name,
  status: projectsTable.status,
  createdAt: projectsTable.createdAt,
  updatedAt: projectsTable.updatedAt,
  // ... כל השדות חוץ מ-previewHtml
};
```

**עדכן בכל route של LIST** (לא GET יחיד):
```typescript
// לפני:
db.select().from(projectsTable)
// אחרי:
db.select(projectsTableMeta).from(projectsTable)
```

---

### 2.3 — הוסף Pagination לרשימת Projects
**קבצים:** `artifacts/api-server/src/routes/projects.ts` — GET `/api/projects`

**הוסף query params:**
```typescript
const page = parseInt(req.query.page as string) || 1;
const limit = Math.min(parseInt(req.query.limit as string) || 20, 100);
const offset = (page - 1) * limit;

const [projects, total] = await Promise.all([
  db.select(projectsTableMeta).from(projectsTable)
    .where(eq(projectsTable.userId, userId))
    .orderBy(desc(projectsTable.updatedAt))
    .limit(limit).offset(offset),
  db.select({ count: count() }).from(projectsTable)
    .where(eq(projectsTable.userId, userId))
]);

res.json({
  projects,
  pagination: { page, limit, total: total[0].count, pages: Math.ceil(total[0].count / limit) }
});
```

---

### 2.4 — הוסף Job Queue אמיתי עם Bull/BullMQ
**קבצים:** יצור `artifacts/api-server/src/lib/queue.ts`

```typescript
// queue.ts
import { Queue, Worker } from 'bullmq';
import IORedis from 'ioredis';

const connection = new IORedis(process.env.REDIS_URL || 'redis://localhost:6379');

export const analysisQueue = new Queue('analysis', { connection });
export const renderQueue = new Queue('render', { connection });

// הגדר Worker:
export const analysisWorker = new Worker('analysis', async (job) => {
  const { projectId, audioPath } = job.data;
  // קרא ל-Python backend
  await callPythonAnalysis(projectId, audioPath);
}, { connection });
```

**ב-package.json של api-server הוסף:**
```json
"bullmq": "^5.0.0",
"ioredis": "^5.0.0"
```

---

## 🟡 PHASE 3 — פיצ'רים חסרים

### 3.1 — Arranger Personas
**קבצים:** `artifacts/music-ai-backend/orchestration/arranger_personas.yaml` (קיים אך לא מיושם), `orchestration/arranger.py`

**יצור את ה-YAML:**
```yaml
personas:
  hasidic_wedding:
    name: "חתונה חסידית"
    description: "סגנון חתונה יהודית מסורתית עם חיות ואנרגיה"
    instruments: [clarinet, violin, accordion, bass, drums]
    rhythm_feel: "freylekhs"
    tempo_range: [120, 180]
    density: high
    key_preference: minor
    chord_extensions: [7th]

  cinematic:
    name: "קולנועי"
    description: "אורקסטרציה קולנועית עם עוצמה ודרמה"
    instruments: [strings, brass, timpani, piano, choir]
    rhythm_feel: "orchestral"
    tempo_range: [60, 120]
    density: evolving
    key_preference: any
    chord_extensions: [9th, sus4]

  jazz_trio:
    name: "ג׳אז טריו"
    instruments: [piano, bass, drums]
    rhythm_feel: "swing"
    tempo_range: [100, 200]
    density: medium
    key_preference: any
    chord_extensions: [9th, 11th, 13th, altered]

  pop_producer:
    name: "פופ מודרני"
    instruments: [synth, bass, drums, guitar, strings_synth]
    rhythm_feel: "straight"
    tempo_range: [90, 130]
    density: medium
    chord_extensions: [add9, maj7]

  ambient:
    name: "אמביינט"
    instruments: [pad, piano, strings, bells]
    rhythm_feel: "free"
    tempo_range: [60, 90]
    density: sparse
    chord_extensions: [maj7, add9, sus2]

  bossa_nova:
    name: "בוסה נובה"
    instruments: [guitar, bass, piano, light_percussion]
    rhythm_feel: "bossa"
    tempo_range: [80, 120]
    density: medium
    chord_extensions: [maj7, min7, 9th]
```

**עדכן `arranger.py`:** טען persona בזמן יצירת arrangement:
```python
from orchestration.persona_loader import load_persona

def arrange(self, analysis: dict, style: str, persona_id: str = None):
    persona = load_persona(persona_id) if persona_id else None
    instruments = persona['instruments'] if persona else self._default_instruments(style)
    # ... המשך הלוגיקה
```

---

### 3.2 — Regenerate-by-Section
**קבצים:** `artifacts/api-server/src/routes/projects.ts`, `artifacts/music-ai-backend/api/routes.py`

**הוסף endpoint ב-Node:**
```typescript
// POST /api/projects/:id/regenerate-section
router.post('/:id/regenerate-section', authMiddleware, async (req, res) => {
  const { sectionLabel, trackFilter } = req.body;
  // sectionLabel: "chorus" | "verse" | "bridge" | etc.
  // trackFilter: optional — null = all tracks, "drums" = drums only

  const job = await createJob(projectId, 'arrangement', {
    mode: 'section',
    sectionLabel,
    trackFilter,
  });
  res.json({ jobId: job.id });
});
```

**ב-Python `arranger.py`:**
```python
def arrange_section(self, analysis: dict, section_label: str,
                    existing_arrangement: dict, track_filter: str = None):
    """Regenerate only a specific section, preserve the rest."""
    new_arrangement = dict(existing_arrangement)  # copy
    target_section = next(
        s for s in analysis['structure']['sections']
        if s['label'] == section_label
    )
    # רץ רק על ה-section הנדרש
    new_tracks = self._generate_tracks(target_section, track_filter)
    new_arrangement['sections'][section_label] = new_tracks
    return new_arrangement
```

---

### 3.3 — Analysis Inspector Page
**קבצים:** יצור `artifacts/music-daw/src/pages/analysis-inspector.tsx`

**הקומפוננט יכלול:**
```tsx
export default function AnalysisInspector({ analysis }: { analysis: AnalysisResult }) {
  return (
    <div className="grid grid-cols-2 gap-4 p-6">
      {/* Tempo Graph */}
      <TempoGraph beats={analysis.rhythm.beatGrid} bpm={analysis.rhythm.bpm} />

      {/* Key Candidates */}
      <KeyCandidates
        globalKey={analysis.key.key}
        candidates={analysis.key.alternatives}
        modulations={analysis.key.modulations}
      />

      {/* Chord Confidence Chart */}
      <ChordConfidenceChart chords={analysis.chords.timeline} />

      {/* Melody Range Visualizer */}
      <MelodyRangeViz
        notes={analysis.melody.notes}
        range={analysis.melody.range}
      />

      {/* Structure Map */}
      <StructureMap
        sections={analysis.structure.sections}
        duration={analysis.duration}
      />

      {/* Vocal Analysis */}
      <VocalPanel
        vocalsDetected={analysis.vocals.detected}
        pitchRange={analysis.vocals.pitchRange}
        vibratoRate={analysis.vocals.vibratoRate}
      />
    </div>
  );
}
```

**הוסף route ב-App.tsx:**
```tsx
<Route path="/project/:id/inspector" element={<AnalysisInspector />} />
```

---

### 3.4 — Export Center Page
**קבצים:** `artifacts/music-daw/src/pages/export-center.tsx` (יצור)

**הקומפוננט:**
```tsx
const EXPORT_FORMATS = [
  { id: 'midi', label: 'MIDI', icon: '🎹', desc: 'Multi-track .mid file' },
  { id: 'musicxml', label: 'MusicXML', icon: '🎼', desc: 'Score notation' },
  { id: 'pdf', label: 'Lead Sheet PDF', icon: '📄', desc: 'Printable chart' },
  { id: 'wav', label: 'WAV', icon: '🔊', desc: '24-bit uncompressed' },
  { id: 'flac', label: 'FLAC', icon: '🔊', desc: 'Lossless compressed' },
  { id: 'mp3', label: 'MP3 320kbps', icon: '🎵', desc: 'Compressed audio' },
  { id: 'stems', label: 'Stems', icon: '🎛️', desc: 'Per-instrument tracks' },
];

export default function ExportCenter({ projectId }: { projectId: string }) {
  const [selected, setSelected] = useState<string[]>([]);
  const { mutate: triggerExport, isLoading } = useExportMutation(projectId);

  return (
    <div className="space-y-6">
      <h2>Export Your Project</h2>
      <div className="grid grid-cols-3 gap-3">
        {EXPORT_FORMATS.map(fmt => (
          <ExportCard
            key={fmt.id}
            format={fmt}
            selected={selected.includes(fmt.id)}
            onToggle={() => toggleFormat(fmt.id)}
          />
        ))}
      </div>
      <Button onClick={() => triggerExport(selected)} disabled={isLoading || selected.length === 0}>
        {isLoading ? 'Exporting...' : `Export ${selected.length} format(s)`}
      </Button>
      <DownloadsList projectId={projectId} />
    </div>
  );
}
```

---

### 3.5 — Tonal Timeline (Modulation Map)
**קבצים:** `artifacts/music-ai-backend/audio/key_mode.py`

**שפר את `detect_modulations`:**
```python
def detect_modulations(self, chroma: np.ndarray, sr: int,
                       hop_length: int = 512, window_bars: int = 4) -> list[dict]:
    """
    Detect key modulations using sliding window chroma analysis.
    Returns list of {time_sec, from_key, to_key, confidence}.
    """
    window_frames = int((60 / self.bpm) * 4 * window_bars * sr / hop_length)
    events = []
    current_key = self.global_key

    for i in range(0, chroma.shape[1] - window_frames, window_frames // 2):
        window = chroma[:, i:i + window_frames]
        key, confidence = self._krumhansl_schmuckler(window.mean(axis=1))

        if key != current_key and confidence > 0.75:
            time_sec = i * hop_length / sr
            events.append({
                "time_sec": round(time_sec, 2),
                "from_key": current_key,
                "to_key": key,
                "confidence": round(float(confidence), 3)
            })
            current_key = key

    return events
```

---

## 🔵 PHASE 4 — שיפורי UI/UX

### 4.1 — MOCK Mode Banner בולט
**קבצים:** `artifacts/music-daw/src/App.tsx` (או `project-studio.tsx`)

```tsx
{project?.isMock && (
  <div className="w-full bg-amber-500 text-black text-center py-2 font-bold text-sm">
    ⚠️ MOCK MODE — תוצאות מדומות בלבד. לא נבוצעה אנליזה אמיתית.
  </div>
)}
```

---

### 4.2 — Job Progress — הצגת Steps ספציפיים
**קבצים:** `artifacts/music-daw/src/components/job-progress.tsx`

**הוסף מיפוי עברי לשלבים:**
```tsx
const STEP_LABELS: Record<string, string> = {
  'ingestion': '📁 טעינה ועיבוד',
  'separation': '🎸 הפרדת קולות',
  'rhythm': '🥁 ניתוח קצב',
  'key': '🎵 זיהוי טונליות',
  'chords': '🎹 ניתוח אקורדים',
  'melody': '🎤 חילוץ מלודיה',
  'structure': '📊 ניתוח מבנה',
  'vocals': '🗣️ ניתוח קולי',
  'arrangement': '🎼 יצירת עיבוד',
  'rendering': '🔊 עיבוד שמע',
};
```

---

### 4.3 — Piano Roll — Zoom Controls
**קבצים:** `artifacts/music-daw/src/components/piano-roll.tsx`

**הוסף:**
```tsx
const [zoom, setZoom] = useState(80); // px per beat, range 20-240

<div className="flex items-center gap-2 p-2 border-b">
  <button onClick={() => setZoom(z => Math.max(20, z - 20))}>-</button>
  <span className="text-xs">{zoom}px/beat</span>
  <button onClick={() => setZoom(z => Math.min(240, z + 20))}>+</button>
  <input
    type="range" min={20} max={240} step={20}
    value={zoom} onChange={e => setZoom(+e.target.value)}
    className="w-24"
  />
</div>
```

---

### 4.4 — Waveform Display עם Section Markers
**קבצים:** `artifacts/music-daw/src/pages/project-studio.tsx`

**שלב WaveSurfer.js:**
```typescript
// npm install wavesurfer.js
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/plugins/regions';

useEffect(() => {
  const ws = WaveSurfer.create({
    container: '#waveform',
    waveColor: '#4f46e5',
    progressColor: '#818cf8',
    plugins: [RegionsPlugin.create()],
  });

  ws.load(`/api/projects/${projectId}/audio`);

  ws.on('ready', () => {
    // הוסף section markers
    analysis?.structure?.sections?.forEach(section => {
      ws.addRegion({
        start: section.start,
        end: section.end,
        color: getSectionColor(section.label),
        content: section.label,
      });
    });
  });

  return () => ws.destroy();
}, [projectId, analysis]);
```

---

## 🟢 PHASE 5 — הכנה ל-Production

### 5.1 — Docker Compose
**יצור:** `docker-compose.yml` בשורש הפרויקט:
```yaml
version: '3.9'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: muzikal
      POSTGRES_USER: muzikal
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U muzikal"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

  api-server:
    build:
      context: ./artifacts/api-server
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql://muzikal:${DB_PASSWORD}@postgres:5432/muzikal
      REDIS_URL: redis://redis:6379
      PYTHON_BACKEND_URL: http://python-backend:8001
      MOCK_MODE: "false"
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

  python-backend:
    build:
      context: ./artifacts/music-ai-backend
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql://muzikal:${DB_PASSWORD}@postgres:5432/muzikal
      REDIS_URL: redis://redis:6379
    ports:
      - "8001:8001"
    volumes:
      - audio_storage:/app/storage
    depends_on:
      - postgres
      - redis

  frontend:
    build:
      context: ./artifacts/music-daw
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - api-server

volumes:
  postgres_data:
  redis_data:
  audio_storage:
```

---

### 5.2 — Dockerfile ל-Python Backend
**יצור:** `artifacts/music-ai-backend/Dockerfile`:
```dockerfile
FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    ffmpeg libsndfile1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

---

### 5.3 — Structured Logging עם Correlation IDs
**קבצים:** `artifacts/api-server/src/lib/logger.ts`, `artifacts/music-ai-backend/api/routes.py`

**ב-Node:**
```typescript
import { randomUUID } from 'crypto';

// Middleware — הוסף ב-app.ts
app.use((req, res, next) => {
  req.correlationId = req.headers['x-correlation-id'] as string || randomUUID();
  res.setHeader('x-correlation-id', req.correlationId);
  next();
});

// כל log call יכלול:
logger.info({ correlationId: req.correlationId, projectId, step }, 'message');
```

**ב-Python:**
```python
import structlog
logger = structlog.get_logger()

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    with structlog.contextvars.bind_contextvars(correlation_id=correlation_id):
        response = await call_next(request)
    return response
```

---

### 5.4 — Object Storage (S3-compatible) במקום /tmp
**יצור:** `artifacts/music-ai-backend/storage/storage_provider.py`:
```python
from abc import ABC, abstractmethod
import boto3, os
from pathlib import Path

class StorageProvider(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> str: ...
    @abstractmethod
    def load(self, key: str) -> bytes: ...
    @abstractmethod
    def get_url(self, key: str, expires: int = 3600) -> str: ...

class LocalStorage(StorageProvider):
    def __init__(self, base_path: str = "/tmp/muzikal"):
        self.base = Path(base_path)
        self.base.mkdir(exist_ok=True)

    def save(self, key: str, data: bytes) -> str:
        path = self.base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def load(self, key: str) -> bytes:
        return (self.base / key).read_bytes()

    def get_url(self, key: str, expires: int = 3600) -> str:
        return f"/api/storage/{key}"  # served via API

class S3Storage(StorageProvider):
    def __init__(self):
        self.client = boto3.client(
            's3',
            endpoint_url=os.getenv('S3_ENDPOINT'),
            aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
        )
        self.bucket = os.getenv('S3_BUCKET', 'muzikal')

    def save(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return f"s3://{self.bucket}/{key}"

    def load(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj['Body'].read()

    def get_url(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': key},
            ExpiresIn=expires
        )

# Factory
def get_storage() -> StorageProvider:
    if os.getenv('S3_ENDPOINT'):
        return S3Storage()
    return LocalStorage()
```

---

## 🧪 PHASE 6 — טסטים חסרים

### 6.1 — טסט ל-Feature Cache
**יצור:** `tests/test_feature_cache.py`:
```python
import pytest, tempfile, os
from packages.audio_core.feature_cache import get_cache_key, load_features, save_features

def test_cache_roundtrip(tmp_path):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake audio data")
    key = get_cache_key(str(audio), "1.1.0")
    features = {"bpm": 120, "key": "C major"}
    save_features(key, features)
    loaded = load_features(key)
    assert loaded == features

def test_cache_miss():
    assert load_features("nonexistent_key") is None

def test_different_files_different_keys(tmp_path):
    f1 = tmp_path / "a.wav"; f1.write_bytes(b"audio1")
    f2 = tmp_path / "b.wav"; f2.write_bytes(b"audio2")
    assert get_cache_key(str(f1), "1.0") != get_cache_key(str(f2), "1.0")
```

---

### 6.2 — טסט ל-Regenerate Section
**יצור:** `tests/test_arranger_section.py`:
```python
def test_regenerate_section_preserves_others():
    arranger = Arranger(style="pop")
    full = arranger.arrange(mock_analysis)
    regenerated = arranger.arrange_section(mock_analysis, "chorus", full)
    # רק chorus השתנה
    assert regenerated['sections']['verse'] == full['sections']['verse']
    assert regenerated['sections']['chorus'] != full['sections']['chorus']
```

---

### 6.3 — Integration Test ל-Pipeline המלא
**קבצים:** `tests/test_full_pipeline.py`
```python
@pytest.mark.integration
async def test_full_pipeline_mock():
    """Test the full pipeline end-to-end with mock audio."""
    response = await client.post('/api/projects', json={'name': 'Test'})
    project_id = response.json()['id']

    # Upload
    with open('tests/fixtures/sample_30sec.mp3', 'rb') as f:
        await client.post(f'/api/projects/{project_id}/upload', files={'audio': f})

    # Analyze
    job = await client.post(f'/api/projects/{project_id}/analyze')
    await wait_for_job(job.json()['jobId'], timeout=60)

    # Verify analysis
    analysis = await client.get(f'/api/projects/{project_id}/analysis')
    assert analysis.json()['rhythm']['bpm'] > 0
    assert analysis.json()['key']['key'] is not None

    # Arrange
    arr_job = await client.post(f'/api/projects/{project_id}/arrange',
                                 json={'style': 'pop'})
    await wait_for_job(arr_job.json()['jobId'], timeout=60)
    arrangement = await client.get(f'/api/projects/{project_id}/arrangement')
    assert len(arrangement.json()['tracks']) > 0
```

---

## 📋 רשימת סדר ביצוע מומלץ

```
PHASE 1 — תיקונים קריטיים (קודם כל, בסדר הזה):
  1.1 → Job schema הוסף עמודות חסרות + push DB
  1.2 → Mock mode fallback שקט → תיקון
  1.3 → WebSocket reconnect loop → תיקון
  1.4 → Audio range requests → תיקון
  1.5 → Analyzer partial failures → תיקון

PHASE 2 — ביצועים:
  2.1 → Feature cache
  2.2 → previewHtml out of SELECT
  2.3 → Pagination
  2.4 → Bull/BullMQ queue (רק אם Redis זמין)

PHASE 3 — פיצ'רים:
  3.1 → Arranger personas YAML
  3.2 → Regenerate-by-section API
  3.3 → Analysis Inspector page
  3.4 → Export Center page
  3.5 → Tonal timeline

PHASE 4 — UI/UX:
  4.1 → Mock banner
  4.2 → Job steps labels (עברי)
  4.3 → Piano roll zoom
  4.4 → WaveSurfer waveform

PHASE 5 — Production:
  5.1 → Docker Compose
  5.2 → Dockerfiles
  5.3 → Correlation IDs logging
  5.4 → Object Storage abstraction

PHASE 6 — טסטים:
  6.1 → Feature cache tests
  6.2 → Regen section tests
  6.3 → Full pipeline integration test
```

---

## ✅ Verification Checklist — לאחר כל Phase

**Phase 1:**
- [ ] `pnpm --filter @workspace/db run push-force` — ללא שגיאות
- [ ] בדוק שבמצב `MOCK_MODE=false` כישלון Python → Job `failed` (לא success)
- [ ] WebSocket: נסה לנתק — לא יותר מ-5 ניסיונות reconnect
- [ ] Audio playback עובד ב-Safari
- [ ] כל 120 טסטים עוברים: `python -m pytest tests/`

**Phase 2:**
- [ ] אנליזה שנייה של אותו קובץ — cache hit בלוג
- [ ] GET `/api/projects` — response לא מכיל שדה `previewHtml`
- [ ] GET `/api/projects?page=2&limit=5` — עובד

**Phase 3:**
- [ ] POST `/api/projects/:id/arrange` עם `personaId: "hasidic_wedding"` — יוצר עיבוד
- [ ] POST `/api/projects/:id/regenerate-section` עם `sectionLabel: "chorus"` — מחזיר jobId
- [ ] דף Analysis Inspector נטען ומציג נתונים

**Phase 5:**
- [ ] `docker compose up` — כל 5 שירותים עולים
- [ ] Logs מכילים `correlationId` בכל request

---

*מסמך זה נוצר אוטומטית מניתוח קוד Muzikal-master. גרסת Pipeline: 1.1.0*
