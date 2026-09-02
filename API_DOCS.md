# 📘 API Developer Documentation

**Base URL (Local):** `http://127.0.0.1:8000`

**Content-Type:** All endpoints accept `multipart/form-data` (NOT `application/json`).

> ⚠️ **Frontend Note:** Use `FormData()` in JavaScript, NOT `JSON.stringify()`.

---

## Endpoints Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/process/short` | Full AI pipeline — transcription, AI analysis, reel extraction, highlights, article |
| `POST` | `/process/long` | Noise cancellation + branding watermark on video (no AI analysis) |

---

## 1. `POST /process/short`

The **main endpoint**. Processes a short-form or interview video through the full AI pipeline.

### Request

**Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | `string` | ✅ Yes | The user's email address. Used to create a unique Cloudinary folder. |
| `file` | `File (.mp4)` | ✅ Yes | The video file to process. |

**JavaScript (Fetch API) Example:**
```javascript
const formData = new FormData();
formData.append("email", "user@gmail.com");
formData.append("file", videoFile); // videoFile = File object from <input type="file">

const response = await fetch("http://127.0.0.1:8000/process/short", {
  method: "POST",
  body: formData,
  // DO NOT set Content-Type header — browser sets it automatically for FormData
});

const data = await response.json();
```

---

### Response

**HTTP 200 OK** — Returns a single JSON object.

```json
{
  "folder": "user_gmail_com/my_video_20240901_103045",
  "status": "success",
  "main_title": "How to Build a Startup in 30 Days",
  "summary": "A comprehensive interview discussing the core principles of building a tech startup from scratch...",
  "article_path": "https://res.cloudinary.com/your_cloud/raw/upload/.../article.md",
  "denoised_video": "https://res.cloudinary.com/your_cloud/video/upload/.../my_video_denoised.mp4",
  "denoised_audio": "https://res.cloudinary.com/your_cloud/video/upload/.../my_video_denoised.mp3",
  "highlights": {
    "title": "The Ultimate Guide to Startup Success",
    "caption": "Everything you need to know about starting your own business, packed into one highlight video! 🚀 #Startup #Entrepreneurship",
    "reason": "This compilation features the most emotionally engaging and educational moments from the interview.",
    "mp4": "https://res.cloudinary.com/your_cloud/video/upload/.../highlights.mp4",
    "mp3": "https://res.cloudinary.com/your_cloud/video/upload/.../highlights.mp3",
    "segments": [
      {
        "start_time": 45.2,
        "end_time": 72.8
      }
    ]
  },
  "reels": [
    {
      "title": "Why 90% of Startups Fail",
      "caption": "The truth nobody tells you about building a business 🚀 #startup #entrepreneur",
      "reason": "Strong hook, emotionally engaging, ends with a clear punchline.",
      "start_time": 120.5,
      "end_time": 148.0,
      "mp4": "https://res.cloudinary.com/your_cloud/video/upload/.../reel_1.mp4",
      "mp3": "https://res.cloudinary.com/your_cloud/video/upload/.../reel_1.mp3"
    },
    {
      "title": "The One Skill Every Founder Needs",
      "caption": "Forget coding. This is what actually matters. #business #founder",
      "reason": "Highly shareable insight, strong opening line.",
      "start_time": 300.1,
      "end_time": 328.4,
      "mp4": "https://res.cloudinary.com/your_cloud/video/upload/.../reel_2.mp4",
      "mp3": "https://res.cloudinary.com/your_cloud/video/upload/.../reel_2.mp3"
    }
  ]
}
```

### Response Field Reference (`/process/short`)

#### Top-Level Fields

| Key | Type | Description |
|-----|------|-------------|
| `folder` | `string` | The Cloudinary folder path where all files are stored. Format: `email/videoname_datetime` |
| `status` | `string` | Always `"success"` on a 200 response. |
| `main_title` | `string` | AI-generated title for the entire video. Use as the main page/post heading. |
| `summary` | `string` | AI-generated 2-3 sentence summary of the full video. |
| `article_path` | `string` | Cloudinary URL to the full AI-written Markdown article (`.md` file). |
| `denoised_video` | `string` | Cloudinary URL to the full noise-cancelled video (with branding logo overlay). |
| `denoised_audio` | `string` | Cloudinary URL to the extracted MP3 audio of the full video. |
| `highlights` | `object` | Object containing the merged highlights compilation. See below. |
| `reels` | `array` | Array of reel objects. Each item is one 20-30 second short-form clip. See below. |

#### `highlights` Object

| Key | Type | Description |
|-----|------|-------------|
| `title` | `string` | AI-generated overarching title for this highlights compilation. |
| `caption` | `string` | AI-generated social media caption for this highlights compilation. |
| `reason` | `string` | AI's reason for grouping these segments together. |
| `mp4` | `string` | Cloudinary URL for the merged highlights video (all best segments in one file). |
| `mp3` | `string` | Cloudinary URL for the audio-only version of the highlights video. |
| `segments` | `array` | Metadata for each individual highlight segment (NO individual video per segment — they are all merged into one `mp4`). |

#### `highlights.segments[]` Item

| Key | Type | Description |
|-----|------|-------------|
| `start_time` | `float` | Start timestamp in seconds (from the original video). |
| `end_time` | `float` | End timestamp in seconds (from the original video). |

#### `reels[]` Item

> Each reel is an **individual, standalone short-form video clip** (20-30 seconds), ready to post to TikTok / Instagram Reels / YouTube Shorts.

| Key | Type | Description |
|-----|------|-------------|
| `title` | `string` | AI-generated title/hook for this reel. |
| `caption` | `string` | AI-generated social media caption with hashtags. Ready to copy-paste. |
| `reason` | `string` | AI's reasoning for why this moment is viral-worthy. |
| `start_time` | `float` | Start timestamp in seconds (from the original video). |
| `end_time` | `float` | End timestamp in seconds (from the original video). |
| `mp4` | `string` | Cloudinary URL for this reel's video file. Use this in a `<video>` tag or download link. |
| `mp3` | `string` | Cloudinary URL for this reel's audio-only file. |

---

## 2. `POST /process/long`

A **lightweight pipeline** that only applies noise cancellation and a branding watermark logo to the video. No AI transcription or analysis is run.

### Request

**Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | `string` | ✅ Yes | The user's email address. Used to create a unique Cloudinary folder. |
| `file` | `File (.mp4)` | ✅ Yes | The video file to process. |

---

### Response

**HTTP 200 OK**

```json
{
  "status": "success",
  "folder": "user_gmail_com/my_video_20240901_103045",
  "video_path": "https://res.cloudinary.com/your_cloud/video/upload/.../my_video_longform.mp4",
  "audio_path": "https://res.cloudinary.com/your_cloud/video/upload/.../my_video_longform.mp3"
}
```

#### Response Field Reference (`/process/long`)

| Key | Type | Description |
|-----|------|-------------|
| `status` | `string` | Always `"success"` on a 200 response. |
| `folder` | `string` | The Cloudinary folder path. |
| `video_path` | `string` | Cloudinary URL for the processed video with branding logo overlay. |
| `audio_path` | `string` | Cloudinary URL for the extracted audio from the processed video. |

---

## Error Responses

Both endpoints return a standard error format on failure.

| HTTP Status | When it happens |
|-------------|-----------------|
| `400` | `email` or `file` field is missing from the request. |
| `500` | The processing pipeline failed (FFmpeg error, AI API timeout, etc.). |

**Error Response Body:**
```json
{
  "detail": "Pipeline failed: [specific error message here]"
}
```

**Frontend Error Handling Example:**
```javascript
if (!response.ok) {
  const error = await response.json();
  console.error("Pipeline error:", error.detail);
}
```

---

## Processing Time Estimates

| Step | Estimated Time |
|------|---------------|
| Audio Extraction & Noise Cancellation | ~5-10 seconds |
| Whisper Transcription | ~10-30 seconds (depends on video length) |
| AI Analysis (GPT-4o-mini) | ~5-10 seconds |
| Reel + Highlight Cutting (parallel FFmpeg) | ~10-20 seconds |
| Cloudinary Upload (parallel) | ~10-30 seconds (depends on file sizes) |
| **Total** | **~40-120 seconds** |

> **Recommendation:** Show a loading spinner/progress bar on the frontend while waiting. Do not set a short timeout on the frontend HTTP client.
