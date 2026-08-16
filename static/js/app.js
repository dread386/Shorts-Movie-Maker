/**
 * Shorts Movie Maker v1.2.0 — Frontend Controller
 * With 8-Grid (A-H) Segmentation, Subtitle & Banner Editor, Style-BERT-VITS2 & High-CTR 9:16 Thumbnails
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const browseBtn = document.getElementById('browseBtn');
  const videoInfoBar = document.getElementById('videoInfoBar');
  const displayFilename = document.getElementById('displayFilename');
  const displaySpecs = document.getElementById('displaySpecs');
  const removeFileBtn = document.getElementById('removeFileBtn');

  const geminiApiKeyInput = document.getElementById('geminiApiKey');
  const customTopicInput = document.getElementById('customTopic');
  const cropModeSelect = document.getElementById('cropMode');
  const gridSettingsPanel = document.getElementById('gridSettingsPanel');
  const gridLayoutSelect = document.getElementById('gridLayoutSelect');
  const gridSlotsContainer = document.getElementById('gridSlotsContainer');
  const gridPreviewImg = document.getElementById('gridPreviewImg');
  const gridPreviewPlaceholder = document.getElementById('gridPreviewPlaceholder');

  const targetDurationSelect = document.getElementById('targetDuration');




  const maxClipsSelect = document.getElementById('maxClips');
  const ttsEngineSelect = document.getElementById('ttsEngine');
  const bannerFontSizeSelect = document.getElementById('bannerFontSize');
  const bannerStyleSelect = document.getElementById('bannerStyle');
  const whisperModelSelect = document.getElementById('whisperModel');
  const showSubtitlesCheckbox = document.getElementById('showSubtitles');
  const showHeaderBannerCheckbox = document.getElementById('showHeaderBanner');
  const customBannerTextInput = document.getElementById('customBannerText');
  const fontKeySelect = document.getElementById('fontKey');
  const displayModeSelect = document.getElementById('displayMode');
  const previewVoiceBtn = document.getElementById('previewVoiceBtn');
  const modalPreviewVoiceBtn = document.getElementById('modalPreviewVoiceBtn');

  const startBtn = document.getElementById('startBtn');

  const stepProgress = document.getElementById('stepProgress');
  const progressPhase = document.getElementById('progressPhase');
  const progressPercent = document.getElementById('progressPercent');
  const progressFill = document.getElementById('progressFill');

  const resultsArea = document.getElementById('resultsArea');
  const clipsGrid = document.getElementById('clipsGrid');
  const zipDownloadBtn = document.getElementById('zipDownloadBtn');

  // Modal Elements
  const subEditorModal = document.getElementById('subEditorModal');
  const modalClipTitle = document.getElementById('modalClipTitle');
  const modalBannerInput = document.getElementById('modalBannerInput');
  const modalBannerFontSize = document.getElementById('modalBannerFontSize');
  const modalTtsEngine = document.getElementById('modalTtsEngine');
  const modalRegenTts = document.getElementById('modalRegenTts');
  const timelineRowsContainer = document.getElementById('timelineRowsContainer');
  const addRowBtn = document.getElementById('addRowBtn');
  const closeModalBtn = document.getElementById('closeModalBtn');
  const cancelModalBtn = document.getElementById('cancelModalBtn');
  const saveAndRerenderBtn = document.getElementById('saveAndRerenderBtn');
  const reRenderBtnText = document.getElementById('reRenderBtnText');

  // Grid definitions
  const GRID_GROUPS = [
    {
      group: '単一区画 (1/4幅 × 1/2高)',
      cells: [
        { key: 'A', label: 'A (左手上・ネック)' },
        { key: 'B', label: 'B (中央左上)' },
        { key: 'C', label: 'C (中央右上・顔)' },
        { key: 'D', label: 'D (右上)' },
        { key: 'E', label: 'E (左手下)' },
        { key: 'F', label: 'F (ピッキング手元)' },
        { key: 'G', label: 'G (ボディ/アンプ)' },
        { key: 'H', label: 'H (右下)' }
      ]
    },
    {
      group: '横2区画ワイド (1/2幅)',
      cells: [
        { key: 'AB', label: 'A+B (上段 左1/2)' },
        { key: 'BC', label: 'B+C (上段 中央1/2)' },
        { key: 'CD', label: 'C+D (上段 右1/2)' },
        { key: 'EF', label: 'E+F (下段 左1/2・手元)' },
        { key: 'FG', label: 'F+G (下段 中央1/2・ギター)' },
        { key: 'GH', label: 'G+H (下段 右1/2)' }
      ]
    },
    {
      group: '横3区画ワイド (3/4幅)',
      cells: [
        { key: 'ABC', label: 'A+B+C (上段 左3/4)' },
        { key: 'BCD', label: 'B+C+D (上段 右3/4・A以外)' },
        { key: 'EFG', label: 'E+F+G (下段 左3/4)' },
        { key: 'FGH', label: 'F+G+H (下段 右3/4・E以外)' }
      ]
    },
    {
      group: '横全幅 (4/4幅)',
      cells: [
        { key: 'ABCD', label: 'A+B+C+D (上段 全幅4/4)' },
        { key: 'EFGH', label: 'E+F+G+H (下段 全幅4/4)' }
      ]
    },
    {
      group: '縦長・ブロック',
      cells: [
        { key: 'AE', label: 'A+E (左端縦長)' },
        { key: 'BF', label: 'B+F (中左縦長)' },
        { key: 'CG', label: 'C+G (中右縦長)' },
        { key: 'DH', label: 'D+H (右端縦長)' },
        { key: 'ABEF', label: '左半分全体 (AB+EF)' },
        { key: 'BCFG', label: '中央半分 (BC+FG)' },
        { key: 'CDGH', label: '右半分全体 (CD+GH)' },
        { key: 'FULL', label: 'FULL (16:9全体フル)' },
        { key: 'CENTER', label: 'CENTER (中央フォーカス)' }
      ]
    }
  ];

  const LAYOUT_SLOT_COUNTS = {
    'split_2_vertical': 2,
    'split_3_vertical': 3,
    'split_4_vertical': 4,
    'grid_2x2': 4,
    'split_2_horizontal': 2
  };

  // Check SBV2 status on load and periodically
  checkTtsStatus();
  setInterval(checkTtsStatus, 10000);

  async function checkTtsStatus() {
    try {
      const res = await fetch('/api/tts_status');
      if (!res.ok) return;
      const data = await res.json();
      if (data.sbv2_online) {
        sbv2Badge.className = 'badge badge-ai';
        sbv2Badge.textContent = `Style-BERT-VITS2: 🟢 起動中 (Port ${data.sbv2_port})`;
      } else {
        sbv2Badge.className = 'badge badge-local';
        sbv2Badge.textContent = 'Style-BERT-VITS2: ⚪ 未起動 (edge-tts併用)';
      }
    } catch (e) {}
  }

  // Load saved API Key from localStorage
  const savedApiKey = localStorage.getItem('shorts_maker_gemini_key');
  if (savedApiKey) {
    geminiApiKeyInput.value = savedApiKey;
  }

  geminiApiKeyInput.addEventListener('change', () => {
    const val = geminiApiKeyInput.value.trim();
    if (val) {
      localStorage.setItem('shorts_maker_gemini_key', val);
    } else {
      localStorage.removeItem('shorts_maker_gemini_key');
    }
  });

  // State
  let currentJobId = null;
  let currentFilename = null;
  let pollInterval = null;
  let editingJobId = null;
  let editingClipIdx = null;
  let lastFocusedSlotIdx = 0;

  // Grid Mode Toggle & Slot Rendering
  cropModeSelect.addEventListener('change', () => {
    if (cropModeSelect.value === 'grid_split') {
      gridSettingsPanel.classList.remove('hidden');
      renderGridSlots(gridLayoutSelect.value);
    } else {
      gridSettingsPanel.classList.add('hidden');
    }
  });

  gridLayoutSelect.addEventListener('change', () => {
    renderGridSlots(gridLayoutSelect.value);
  });

  // Render Slots dynamically with optgroups
  function renderGridSlots(layoutKey, presetValues = null) {
    const count = LAYOUT_SLOT_COUNTS[layoutKey] || 2;
    gridSlotsContainer.innerHTML = '';

    const defaultAssignments = presetValues || (
      layoutKey === 'split_2_vertical' ? ['A', 'F'] :
      layoutKey === 'split_3_vertical' ? ['C', 'A', 'F'] :
      layoutKey === 'grid_2x2' ? ['A', 'B', 'E', 'F'] :
      layoutKey === 'split_4_vertical' ? ['A', 'B', 'E', 'F'] :
      ['A', 'F']
    );

    for (let i = 0; i < count; i++) {
      const slotDiv = document.createElement('div');
      slotDiv.className = 'grid-slot-row';
      
      const slotLabel = layoutKey === 'split_2_vertical' ? (i === 0 ? '上段 スロット 1' : '下段 スロット 2') :
                        layoutKey === 'split_3_vertical' ? (i === 0 ? '上段 (顔/上)' : i === 1 ? '中段 (左手)' : '下段 (右手)') :
                        layoutKey === 'grid_2x2' ? (i === 0 ? '左上' : i === 1 ? '右上' : i === 2 ? '左下' : '右下') :
                        `スロット ${i + 1}`;

      const selectedVal = defaultAssignments[i] || 'A';

      let optionsHtml = '';
      GRID_GROUPS.forEach(grp => {
        optionsHtml += `<optgroup label="${grp.group}">`;
        grp.cells.forEach(c => {
          const isSel = c.key === selectedVal ? 'selected' : '';
          optionsHtml += `<option value="${c.key}" ${isSel}>${c.label}</option>`;
        });
        optionsHtml += `</optgroup>`;
      });

      slotDiv.innerHTML = `
        <span class="slot-badge">${slotLabel}</span>
        <select class="modal-select slot-select" data-slot-index="${i}">
          ${optionsHtml}
        </select>
      `;

      const selElem = slotDiv.querySelector('.slot-select');
      selElem.addEventListener('focus', () => {
        lastFocusedSlotIdx = i;
      });

      gridSlotsContainer.appendChild(slotDiv);
    }
  }

  // Interactive clicking on visual grid cells to assign to currently focused slot
  document.querySelectorAll('.grid-cell').forEach(cell => {
    cell.addEventListener('click', () => {
      const cellKey = cell.getAttribute('data-cell');
      const allSlotSelects = document.querySelectorAll('#gridSlotsContainer .slot-select');
      if (allSlotSelects.length > 0) {
        const targetSel = allSlotSelects[lastFocusedSlotIdx] || allSlotSelects[0];
        targetSel.value = cellKey;
        
        // Visual feedback
        cell.style.borderColor = '#38BDF8';
        cell.style.background = 'rgba(56, 189, 248, 0.4)';
        setTimeout(() => {
          cell.style.borderColor = '';
          cell.style.background = '';
        }, 300);

        // Move to next slot
        lastFocusedSlotIdx = (lastFocusedSlotIdx + 1) % allSlotSelects.length;
      }
    });
  });

  // Presets
  document.querySelectorAll('.btn-preset').forEach(btn => {
    btn.addEventListener('click', () => {
      const p = btn.getAttribute('data-preset');
      if (p === 'guitar_2') {
        gridLayoutSelect.value = 'split_2_vertical';
        renderGridSlots('split_2_vertical', ['A', 'F']);
      } else if (p === 'guitar_3') {
        gridLayoutSelect.value = 'split_3_vertical';
        renderGridSlots('split_3_vertical', ['C', 'A', 'F']);
      } else if (p === 'grid_4') {
        gridLayoutSelect.value = 'grid_2x2';
        renderGridSlots('grid_2x2', ['A', 'B', 'E', 'F']);
      }
    });
  });

  // Initial Grid Slots render
  renderGridSlots('split_2_vertical');

  // 1. Drag & Drop handlers
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  });

  dropzone.addEventListener('click', () => fileInput.click());
  browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFileUpload(fileInput.files[0]);
    }
  });

  removeFileBtn.addEventListener('click', () => {
    resetUpload();
  });

  function resetUpload() {

    currentJobId = null;
    currentFilename = null;
    fileInput.value = '';
    videoInfoBar.classList.add('hidden');
    dropzone.classList.remove('hidden');
    
    if (gridPreviewImg) {
      gridPreviewImg.src = '';
    }
    if (gridPreviewPlaceholder) {
      gridPreviewPlaceholder.classList.remove('hidden');
    }
    startBtn.disabled = true;
  }

  // Generate instant thumbnail from local video file using Canvas
  function generateClientThumbnail(file) {
    try {
      const video = document.createElement('video');
      video.preload = 'auto';
      video.src = URL.createObjectURL(file);
      video.muted = true;
      video.playsInline = true;
      
      video.onloadedmetadata = () => {
        const seekTime = Math.min(2.0, Math.max(0.5, (video.duration || 10) * 0.1));
        video.currentTime = seekTime;
      };

      video.onseeked = () => {
        try {
          const canvas = document.createElement('canvas');
          canvas.width = video.videoWidth || 1280;
          canvas.height = video.videoHeight || 720;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
          if (dataUrl && dataUrl.length > 500) {
            gridPreviewImg.src = dataUrl;
            gridPreviewPlaceholder.classList.add('hidden');
          }
        } catch (err) {
          console.warn('Canvas render error', err);
        } finally {
          URL.revokeObjectURL(video.src);
        }
      };

      video.onerror = () => {
        URL.revokeObjectURL(video.src);
      };
    } catch (e) {
      console.warn('Client thumbnail error', e);
    }
  }

  // 2. Upload File to Backend
  async function handleFileUpload(file) {
    displayFilename.textContent = `アップロード中: ${file.name}...`;
    displaySpecs.textContent = "サーバーに送信中...";
    videoInfoBar.classList.remove('hidden');
    dropzone.classList.add('hidden');

    // 1. Instant local thumbnail generation (0.05s)
    generateClientThumbnail(file);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const resp = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || 'アップロードに失敗しました');
      }

      const data = await resp.json();
      currentJobId = data.job_id;
      currentFilename = data.filename;

      const durSec = data.video_info.duration || 0;
      const min = Math.floor(durSec / 60);
      const sec = Math.floor(durSec % 60);
      const durStr = `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;

      displayFilename.textContent = file.name;
      displaySpecs.textContent = `長さ: ${durStr} | 解像度: ${data.video_info.width}x${data.video_info.height} | ${data.video_info.fps}fps`;

      // 2. Apply high-quality FFmpeg extracted base64 image (100% reliable)
      if (data.preview_image_base64) {
        gridPreviewImg.src = data.preview_image_base64;
        gridPreviewPlaceholder.classList.add('hidden');
      } else if (data.preview_image_url) {
        gridPreviewImg.src = `${data.preview_image_url}?t=${Date.now()}`;
        gridPreviewPlaceholder.classList.add('hidden');
      }

      startBtn.disabled = false;
    } catch (e) {
      alert(`エラー: ${e.message}`);
      resetUpload();
    }
  }




  // Helper to parse TTS value
  function parseTtsValue(val) {
    if (!val || val === 'off') {
      return { ttsEngine: 'off', ttsModel: '', ttsEnabled: false };
    }
    const parts = val.split(':');
    return {
      ttsEngine: parts[0],
      ttsModel: parts.slice(1).join(':'),
      ttsEnabled: true
    };
  }

  // Voice Preview synthesis & playback
  async function previewVoice(selectVal, btnElem) {
    const { ttsEngine, ttsModel } = parseTtsValue(selectVal);
    if (ttsEngine === 'off') {
      alert('「なし」が選択されているため、音声は生成されません。');
      return;
    }
    const origText = btnElem.textContent;
    btnElem.textContent = '⏳ 合成中...';
    btnElem.disabled = true;

    try {
      const resp = await fetch('/api/tts_preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tts_engine: ttsEngine,
          tts_model: ttsModel,
          text: 'ショート動画を自動生成します'
        })
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '合成エラー');
      }

      const data = await resp.json();
      if (data.audio_base64) {
        const audio = new Audio(data.audio_base64);
        btnElem.textContent = '🔊 再生中...';
        audio.onended = () => {
          btnElem.textContent = origText;
          btnElem.disabled = false;
        };
        audio.onerror = () => {
          btnElem.textContent = origText;
          btnElem.disabled = false;
        };
        await audio.play();
      }
    } catch (e) {
      alert(`試聴エラー: ${e.message}`);
      btnElem.textContent = origText;
      btnElem.disabled = false;
    }
  }

  if (previewVoiceBtn) {
    previewVoiceBtn.addEventListener('click', () => {
      previewVoice(ttsEngineSelect.value, previewVoiceBtn);
    });
  }

  if (modalPreviewVoiceBtn) {
    modalPreviewVoiceBtn.addEventListener('click', () => {
      previewVoice(modalTtsEngine.value, modalPreviewVoiceBtn);
    });
  }


  // 3. Start Processing
  startBtn.addEventListener('click', async () => {
    if (!currentJobId || !currentFilename) return;

    const apiKey = geminiApiKeyInput.value.trim();
    if (apiKey) {
      localStorage.setItem('shorts_maker_gemini_key', apiKey);
    }

    const { ttsEngine, ttsModel, ttsEnabled } = parseTtsValue(ttsEngineSelect.value);

    // Collect grid slots
    const gridSlots = [];
    document.querySelectorAll('#gridSlotsContainer .slot-select').forEach(sel => {
      gridSlots.push(sel.value);
    });

    const settings = {
      gemini_api_key: apiKey,
      custom_topic: customTopicInput.value.trim(),
      target_duration: parseFloat(targetDurationSelect.value),
      max_clips: parseInt(maxClipsSelect.value, 10),
      crop_mode: cropModeSelect.value,
      grid_layout: gridLayoutSelect.value,
      grid_slots: gridSlots,
      tts_enabled: ttsEnabled,
      tts_engine: ttsEngine,
      tts_model: ttsModel,
      banner_font_size: parseInt(bannerFontSizeSelect.value, 10),
      banner_style: bannerStyleSelect.value,
      whisper_model: whisperModelSelect.value,
      show_subtitles: showSubtitlesCheckbox.checked,
      show_header_banner: showHeaderBannerCheckbox.checked,
      custom_banner_text: customBannerTextInput.value.trim(),
      font_key: fontKeySelect.value,
      display_mode: displayModeSelect.value
    };

    startBtn.disabled = true;
    stepProgress.classList.remove('hidden');
    resultsArea.classList.add('hidden');
    clipsGrid.innerHTML = '';
    updateProgress(0.01, 'ジョブを開始中...');

    stepProgress.scrollIntoView({ behavior: 'smooth' });

    try {
      const resp = await fetch('/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: currentJobId,
          filename: currentFilename,
          settings: settings
        })
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '処理開始に失敗しました');
      }

      startPolling(currentJobId);
    } catch (e) {
      alert(`処理開始エラー: ${e.message}`);
      startBtn.disabled = false;
    }
  });

  // 4. Polling Status
  function startPolling(jobId) {
    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(async () => {
      try {
        const resp = await fetch(`/api/status/${jobId}`);
        if (!resp.ok) return;

        const data = await resp.json();
        updateProgress(data.progress, data.phase);

        if (data.status === 'done') {
          clearInterval(pollInterval);
          renderResults(jobId, data.clips);
          startBtn.disabled = false;
        } else if (data.status === 'error') {
          clearInterval(pollInterval);
          alert(`処理中にエラーが発生しました: ${data.error}`);
          startBtn.disabled = false;
        }
      } catch (e) {
        console.error('Polling error', e);
      }
    }, 1500);
  }

  function updateProgress(progress, phase) {
    const pct = Math.min(100, Math.max(0, Math.round((progress || 0) * 100)));
    progressPercent.textContent = `${pct}%`;
    progressFill.style.width = `${pct}%`;
    if (phase) {
      progressPhase.textContent = phase;
    }
  }

  // 5. Render Completed Clips
  function renderResults(jobId, clips) {
    resultsArea.classList.remove('hidden');
    zipDownloadBtn.href = `/api/download_zip/${jobId}`;
    clipsGrid.innerHTML = '';

    if (!clips || clips.length === 0) {
      clipsGrid.innerHTML = '<p class="text-muted">クリップが生成されませんでした。</p>';
      return;
    }

    clips.forEach(c => {
      const card = document.createElement('div');
      card.className = 'clip-card';
      card.id = `clipCard_${c.index}`;

      card.innerHTML = `
        <div class="clip-media-tabs">
          <div class="clip-video-wrap">
            <video controls preload="metadata" playsinline id="videoElem_${c.index}">
              <source src="${c.video_url}" type="video/mp4">
              お使いのブラウザは動画タグに対応していません。
            </video>
            <span class="clip-duration-badge">${c.duration}s</span>
          </div>
          ${c.thumbnail_url ? `
            <div class="clip-thumb-preview-wrap">
              <img src="${c.thumbnail_url}" alt="9:16 サムネイル" class="clip-thumb-img" id="thumbImg_${c.index}">
              <span class="thumb-badge">9:16 サムネイル</span>
            </div>
          ` : ''}
        </div>
        <div class="clip-body">
          <h4 class="clip-title" id="cardTitle_${c.index}">${escapeHtml(c.title)}</h4>
          ${c.banner_text ? `<p class="clip-hook" id="cardHook_${c.index}">💡 ${escapeHtml(c.banner_text)}</p>` : ''}
          ${c.summary ? `<p class="clip-summary">${escapeHtml(c.summary)}</p>` : ''}
          <div class="clip-actions">
            <button type="button" class="btn-edit-sub" onclick="openSubtitleEditor('${jobId}', ${c.index})">✏️ 字幕＆バナー編集</button>
            <a href="${c.video_url}" download="${c.filename}" class="btn-clip-dl" id="dlBtn_${c.index}">⬇ 動画</a>
            ${c.thumbnail_url ? `<a href="${c.thumbnail_url}" download="${c.thumb_filename || `thumb_${c.index}.png`}" class="btn-clip-thumb" id="thumbBtn_${c.index}">🖼️ サムネ</a>` : ''}
            <a href="${c.srt_url}" download="clip_${c.index}.srt" class="btn-clip-srt" id="srtBtn_${c.index}">SRT</a>
          </div>
        </div>
      `;

      clipsGrid.appendChild(card);
    });
  }

  // 6. In-App Subtitle & Banner Editor Modal
  window.openSubtitleEditor = async function(jobId, clipIdx) {
    editingJobId = jobId;
    editingClipIdx = clipIdx;
    modalClipTitle.textContent = `クリップ #${clipIdx} — 字幕＆バナー編集`;
    timelineRowsContainer.innerHTML = '<p class="text-muted">字幕データを読み込み中...</p>';
    modalBannerInput.value = '';
    
    // Sync current UI values into modal
    modalBannerFontSize.value = bannerFontSizeSelect.value || "76";
    modalTtsEngine.value = ttsEngineSelect.value || "edge_tts:ja-JP-KeitaNeural";
    subEditorModal.classList.remove('hidden');


    try {
      const resp = await fetch(`/api/clips/timeline/${jobId}/${clipIdx}`);
      if (!resp.ok) throw new Error('字幕データの取得に失敗しました');

      const data = await resp.json();
      modalBannerInput.value = data.banner_text || '';
      renderTimelineRows(data.timeline || []);
    } catch (e) {
      alert(`エラー: ${e.message}`);
      closeModal();
    }
  };

  function renderTimelineRows(timeline) {
    timelineRowsContainer.innerHTML = '';
    if (timeline.length === 0) {
      timelineRowsContainer.innerHTML = '<p class="text-muted">字幕行がありません。「＋ 行を追加」で追加できます。</p>';
      return;
    }

    timeline.forEach((item) => {
      addTimelineRowElement(item.start, item.end, item.text);
    });
  }

  function addTimelineRowElement(start = 0.0, end = 2.0, text = '') {
    const row = document.createElement('div');
    row.className = 'sub-edit-row';
    row.innerHTML = `
      <input type="number" step="0.1" min="0" class="sub-time-input sub-start" value="${start}" title="開始秒">
      <span style="color:var(--text-dim)">〜</span>
      <input type="number" step="0.1" min="0" class="sub-time-input sub-end" value="${end}" title="終了秒">
      <input type="text" class="sub-text-input" value="${escapeHtml(text)}" placeholder="字幕テキストを入力...">
      <button type="button" class="btn-delete-row" title="この行を削除">✕</button>
    `;

    row.querySelector('.btn-delete-row').addEventListener('click', () => {
      row.remove();
    });

    timelineRowsContainer.appendChild(row);
  }

  addRowBtn.addEventListener('click', () => {
    const rows = timelineRowsContainer.querySelectorAll('.sub-edit-row');
    let lastEnd = 0.0;
    if (rows.length > 0) {
      const lastEndInput = rows[rows.length - 1].querySelector('.sub-end');
      lastEnd = parseFloat(lastEndInput.value) || 0.0;
    }
    addTimelineRowElement(roundNum(lastEnd), roundNum(lastEnd + 2.5), '');
  });

  function closeModal() {
    subEditorModal.classList.add('hidden');
    editingJobId = null;
    editingClipIdx = null;
  }

  closeModalBtn.addEventListener('click', closeModal);
  cancelModalBtn.addEventListener('click', closeModal);

  // Save & Re-render (Banner + Voiceover + Subtitles + Thumbnail)
  saveAndRerenderBtn.addEventListener('click', async () => {
    if (!editingJobId || !editingClipIdx) return;

    // Collect rows
    const rows = timelineRowsContainer.querySelectorAll('.sub-edit-row');
    const newTimeline = [];

    rows.forEach(r => {
      const s = parseFloat(r.querySelector('.sub-start').value) || 0.0;
      const e = parseFloat(r.querySelector('.sub-end').value) || 0.0;
      const t = r.querySelector('.sub-text-input').value.trim();
      if (t) {
        newTimeline.push({
          start: roundNum(s),
          end: roundNum(e),
          text: t
        });
      }
    });

    newTimeline.sort((a, b) => a.start - b.start);

    const updatedBannerText = modalBannerInput.value.trim();
    const regenTts = modalRegenTts.checked;
    const { ttsEngine, ttsModel } = parseTtsValue(modalTtsEngine.value);
    const bannerFontSize = parseInt(modalBannerFontSize.value, 10) || 76;

    saveAndRerenderBtn.disabled = true;

    reRenderBtnText.textContent = '⏳ 再レンダリング中 (動画+音声+サムネ)...';

    try {
      const resp = await fetch(`/api/clips/re-render/${editingJobId}/${editingClipIdx}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          timeline: newTimeline,
          banner_text: updatedBannerText,
          banner_font_size: bannerFontSize,
          tts_engine: ttsEngine,
          tts_model: ttsModel,
          regenerate_tts: regenTts
        })
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '再生成に失敗しました');
      }

      const data = await resp.json();

      // Update elements immediately
      const videoElem = document.getElementById(`videoElem_${editingClipIdx}`);
      const thumbImg = document.getElementById(`thumbImg_${editingClipIdx}`);
      const dlBtn = document.getElementById(`dlBtn_${editingClipIdx}`);
      const thumbBtn = document.getElementById(`thumbBtn_${editingClipIdx}`);
      const srtBtn = document.getElementById(`srtBtn_${editingClipIdx}`);
      const cardHook = document.getElementById(`cardHook_${editingClipIdx}`);

      if (videoElem) {
        videoElem.src = data.video_url;
        videoElem.load();
      }
      if (thumbImg && data.thumbnail_url) {
        thumbImg.src = data.thumbnail_url;
      }
      if (dlBtn) dlBtn.href = data.video_url;
      if (thumbBtn && data.thumbnail_url) thumbBtn.href = data.thumbnail_url;
      if (srtBtn) srtBtn.href = data.srt_url;
      if (cardHook && updatedBannerText) {
        cardHook.textContent = `💡 ${updatedBannerText}`;
      }

      closeModal();
      alert(`クリップ #${editingClipIdx} の動画・音声・サムネイルを再反映しました！🎉`);
    } catch (e) {
      alert(`エラー: ${e.message}`);
    } finally {
      saveAndRerenderBtn.disabled = false;
      reRenderBtnText.textContent = '🔄 修正して動画＆サムネに再反映 (即時)';
    }
  });

  function roundNum(n) {
    return Math.round(n * 10) / 10;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
