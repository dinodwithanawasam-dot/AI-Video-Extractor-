# 📘 AI Video Extractor — API Developer Documentation

**Version:** 1.0  
**Base URL (Local):** `http://127.0.0.1:8000`  
**Base URL (Docker):** `http://localhost:8000`

> ⚠️ **Critical Note for Frontend:** All endpoints accept **`multipart/form-data`** only — NOT `application/json`.  
> Always use `FormData()` in JavaScript. Never use `JSON.stringify()`.

---

## Endpoints Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Check if the API server and Whisper model are ready |
| `POST` | `/process/short` | **Main pipeline** — Full AI analysis, reels, highlights & article |
| `POST` | `/process/long` | Lightweight pipeline — Noise cancellation + branding watermark only |

---

## 1. `GET /health`

Use this before uploading to confirm the server is ready. The Whisper AI model takes ~5 seconds to load on startup.

### Request
No body required.

```javascript
const res = await fetch("http://localhost:8000/health");
const data = await res.json();
```

### Response

```json
{
  "status": "ok",
  "whisper_model_loaded": true
}
```

| Key | Type | Description |
|-----|------|-------------|
| `status` | `string` | `"ok"` when ready, `"starting"` while Whisper model is still loading |
| `whisper_model_loaded` | `boolean` | `true` once the AI model is ready to process audio |

> **Tip:** Poll this endpoint on page load and only show the upload button when `status === "ok"`.

---

## 2. `POST /process/short`

The **main endpoint**. Runs the full AI pipeline on an uploaded video:
1. Extracts & denoises audio  
2. Transcribes audio with Whisper AI (runs in parallel with video branding)
3. Analyzes transcript with GPT-4o-mini  
4. Cuts viral reels (20-30 sec each)  
5. Merges highlight segments into one video  
6. Generates a written article  
7. Uploads everything to Cloudinary  

All output files are **automatically deleted from the server** after upload.

### Request

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | `string` | ✅ Yes | User's email. Used to create a unique Cloudinary storage folder. |
| `file` | `File (.mp4)` | ✅ Yes | The video file to process. |

**JavaScript Example:**
```javascript
const formData = new FormData();
formData.append("email", "user@example.com");
formData.append("file", videoFile); // File object from <input type="file">

const response = await fetch("http://localhost:8000/process/short", {
  method: "POST",
  body: formData,
  // ⚠️ Do NOT set Content-Type header — the browser handles it automatically
});

if (!response.ok) {
  const err = await response.json();
  throw new Error(err.detail);
}

const data = await response.json();
```

**TypeScript Types:**
```typescript
interface HighlightSegment {
  start_time: number;
  end_time: number;
}

interface Highlights {
  title: string;
  caption: string;
  reason: string;
  mp4: string;
  mp3: string;
  segments: HighlightSegment[];
}

interface Reel {
  title: string;
  caption: string;
  reason: string;
  start_time: number;
  end_time: number;
  mp4: string;
  mp3: string;
}

interface ShortFormResponse {
  folder: string;
  status: string;
  main_title: string;
  summary: string;
  article_path: string;
  denoised_video: string;
  denoised_audio: string;
  highlights: Highlights;
  reels: Reel[];
}
```

---

### Response — HTTP 200 OK

```json
{
  "folder": "user_example_com/interview_20260901_103045",
  "status": "success",
  "main_title": "How to Build a Startup in 30 Days",
  "summary": "A comprehensive interview discussing the core principles of building a tech startup from scratch, featuring insights on fundraising, team building, and product-market fit.",
  "article_path": "https://res.cloudinary.com/dakae2qgl/raw/upload/.../article.md",
  "denoised_video": "https://res.cloudinary.com/dakae2qgl/video/upload/.../1_longform.mp4",
  "denoised_audio": "https://res.cloudinary.com/dakae2qgl/video/upload/.../1.mp3",
  "highlights": {
    "title": "The Ultimate Guide to Startup Success",
    "caption": "Everything you need to know about starting your own business! 🚀 #Startup #Entrepreneurship #Founder",
    "reason": "These segments capture the most emotionally engaging and actionable moments of the interview.",
    "mp4": "https://res.cloudinary.com/dakae2qgl/video/upload/.../highlights.mp4",
    "mp3": "https://res.cloudinary.com/dakae2qgl/video/upload/.../highlights.mp3",
    "segments": [
      { "start_time": 61.0, "end_time": 79.0 },
      { "start_time": 115.0, "end_time": 137.0 },
      { "start_time": 160.0, "end_time": 179.0 }
    ]
  },
  "reels": [
    {
      "title": "Why 90% of Startups Fail",
      "caption": "The truth nobody tells you about building a business 🚀 #startup #entrepreneur",
      "reason": "Strong hook, emotionally engaging, ends with a clear punchline.",
      "start_time": 50.0,
      "end_time": 79.0,
      "mp4": "https://res.cloudinary.com/dakae2qgl/video/upload/.../reel_1.mp4",
      "mp3": "https://res.cloudinary.com/dakae2qgl/video/upload/.../reel_1.mp3"
    },
    {
      "title": "The One Skill Every Founder Needs",
      "caption": "Forget coding. This is what actually matters. #business #founder",
      "reason": "Highly shareable insight with a strong opening line.",
      "start_time": 115.0,
      "end_time": 143.0,
      "mp4": "https://res.cloudinary.com/dakae2qgl/video/upload/.../reel_2.mp4",
      "mp3": "https://res.cloudinary.com/dakae2qgl/video/upload/.../reel_2.mp3"
    }
  ]
}
```

---

### Response Field Reference

#### Top-Level Fields

| Key | Type | Description |
|-----|------|-------------|
| `folder` | `string` | Cloudinary folder path. Format: `email_sanitized/filename_YYYYMMDD_HHMMSS` |
| `status` | `string` | Always `"success"` on HTTP 200. |
| `main_title` | `string` | AI-generated title for the entire video. Use as the main heading. |
| `summary` | `string` | AI-generated 2-3 sentence summary of the full video. |
| `article_path` | `string` | Cloudinary URL to the full AI-written Markdown article (`.md` file). Fetch and render with a Markdown library. |
| `denoised_video` | `string` | Cloudinary URL to the full processed video — noise cancelled, branding logo, and intro/outro applied. |
| `denoised_audio` | `string` | Cloudinary URL to the extracted MP3 of the full video. |
| `highlights` | `object` | The merged highlights compilation. See below. |
| `reels` | `array` | Array of 2-3 short-form reel clips (20-30 seconds each). See below. |

#### `highlights` Object

| Key | Type | Description |
|-----|------|-------------|
| `title` | `string` | AI-generated title for the highlights compilation. |
| `caption` | `string` | Ready-to-post social media caption with hashtags for the highlights video. |
| `reason` | `string` | AI's explanation of why these segments were selected together. |
| `mp4` | `string` | Cloudinary URL for the compiled highlights video (all best moments merged into one file). |
| `mp3` | `string` | Cloudinary URL for the audio-only version of the highlights video. |
| `segments` | `array` | Timestamps of each merged segment. **No individual video per segment** — all merged into the single `mp4`. |

#### `highlights.segments[]` Item

| Key | Type | Description |
|-----|------|-------------|
| `start_time` | `float` | Start timestamp in seconds (from the original uploaded video). |
| `end_time` | `float` | End timestamp in seconds (from the original uploaded video). |

#### `reels[]` Item

> Each reel is an **individual, standalone short-form video** (20-30 seconds) with branding logo + intro/outro applied. Ready to post to TikTok / Instagram Reels / YouTube Shorts.

| Key | Type | Description |
|-----|------|-------------|
| `title` | `string` | AI-generated viral-style title/hook for this reel. |
| `caption` | `string` | Ready-to-post social media caption with 3-5 hashtags. |
| `reason` | `string` | AI's reasoning for why this moment is shareable/viral. |
| `start_time` | `float` | Start timestamp in seconds (from the original video). |
| `end_time` | `float` | End timestamp in seconds (from the original video). |
| `mp4` | `string` | Cloudinary URL for this reel's video. Use directly in a `<video>` tag. |
| `mp3` | `string` | Cloudinary URL for this reel's audio-only file. |

---

## 3. `POST /process/long`

A **lightweight pipeline** that applies noise cancellation, branding watermark logo, and intro/outro sequences. No AI transcription or analysis. Use for long-form recordings where you only need a clean, branded video.

### Request

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | `string` | ✅ Yes | User's email. Used to create a unique Cloudinary folder. |
| `file` | `File (.mp4)` | ✅ Yes | The video file to process. |

**JavaScript Example:**
```javascript
const formData = new FormData();
formData.append("email", "user@example.com");
formData.append("file", videoFile);

const response = await fetch("http://localhost:8000/process/long", {
  method: "POST",
  body: formData,
});

const data = await response.json();
```

---

### Response — HTTP 200 OK

```json
{
  "status": "success",
  "folder": "user_example_com/interview_20260901_103045",
  "video_path": "https://res.cloudinary.com/dakae2qgl/video/upload/.../interview_longform.mp4",
  "audio_path": "https://res.cloudinary.com/dakae2qgl/video/upload/.../interview_longform.mp3"
}
```

#### Response Fields

| Key | Type | Description |
|-----|------|-------------|
| `status` | `string` | Always `"success"` on HTTP 200. |
| `folder` | `string` | Cloudinary folder path for all output files. |
| `video_path` | `string` | Cloudinary URL for the processed video (noise-cancelled, logo, intro/outro applied). |
| `audio_path` | `string` | Cloudinary URL for the extracted audio (MP3) from the processed video. |

---

## Error Responses

Both `POST` endpoints return the same error format on failure.

| HTTP Status | When it happens |
|-------------|-----------------|
| `400 Bad Request` | `email` or `file` field is missing from the request. |
| `500 Internal Server Error` | Pipeline failed — FFmpeg error, AI API timeout, Cloudinary upload error, etc. |

**Error Response Body:**
```json
{
  "detail": "Pipeline failed: [specific error message]"
}
```

**Frontend Error Handling:**
```javascript
const response = await fetch("http://localhost:8000/process/short", {
  method: "POST",
  body: formData,
});

if (!response.ok) {
  const error = await response.json();
  console.error("Error:", error.detail);
  // Show error.detail to the user
  return;
}

const data = await response.json();
// Handle success
```

---

## Processing Time Estimates

> ⏳ The `/process/short` endpoint runs a heavy AI pipeline. The frontend **must** show a loading state. Do NOT set a short HTTP timeout — use at least **10 minutes**.

| Step | Estimated Time |
|------|----------------|
| Video Upload to Server | Depends on file size & internet speed |
| Audio Extraction & Noise Cancellation | ~5-10 seconds |
| Video Branding (logo + intro/outro render) *(parallel)* | ~30-90 seconds |
| Whisper AI Transcription *(parallel with above)* | ~60-120 seconds on CPU |
| GPT-4o-mini Transcript Analysis | ~5-10 seconds |
| Article Generation | ~5-10 seconds |
| Reel Cutting — 3 reels in parallel FFmpeg | ~15-30 seconds |
| Highlights Compilation | ~10-20 seconds |
| Cloudinary Upload — 11 files in parallel | ~20-60 seconds |
| **Total End-to-End** | **~3 to 6 minutes** |

**Recommended Frontend UX — Status messages to cycle through:**
```javascript
const steps = [
  "Uploading your video...",
  "Extracting and denoising audio...",
  "Transcribing with AI...",
  "Analyzing content with GPT...",
  "Cutting viral reels...",
  "Compiling highlights...",
  "Uploading to cloud storage...",
  "Almost done!",
];
```

---

## Branding & Media Notes

All output videos automatically include (applied server-side, frontend does nothing):
- **Intro video** — `media/video/start.mp4` prepended to the beginning
- **Outro video** — `media/video/end.mp4` appended to the end  
- **Branding logo** — `logo/branding.jpeg` watermarked in the top-right corner
- **Noise-cancelled audio** — Applied using FFmpeg's `afftdn` filter

---

## Cloudinary URL Notes

All media URLs (`mp4`, `mp3`, `article_path`, etc.) are **direct Cloudinary CDN links**:

```html
<!-- Video -->
<video src="https://res.cloudinary.com/dakae2qgl/video/upload/.../reel_1.mp4" controls></video>

<!-- Audio -->
<audio src="https://res.cloudinary.com/dakae2qgl/video/upload/.../reel_1.mp3" controls></audio>
```

- URLs are **permanent** and publicly accessible (no auth required)
- Fetch the `.md` article file and render with a Markdown library (e.g. `react-markdown`)
