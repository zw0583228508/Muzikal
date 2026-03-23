EXTRACTION_PROMPT = """
You are a musicologist assistant. Extract musical style parameters from the user message.

User message: {text}

Known genres in database: {known_genres}

Already collected params: {current_params}

Return ONLY valid JSON with any of these fields you can identify:
{{
  "genre": "...",
  "era": "...",
  "sub_style": "...",
  "region": "...",
  "mood": "...",
  "tempo_feel": "fast|medium|slow",
  "instrumentation_hint": "...",
  "reference_artist": "...",
  "reference_piece": "..."
}}

If a field is unknown, omit it. Never guess if uncertain.
Return ONLY the JSON object, no explanation.
"""

ENRICHMENT_PROMPT = """
You are an expert musicologist and arranger with encyclopedic knowledge of world music.

Style request: {genre} / {sub_style} / {era} / {region}
Base YAML data: {base_yaml}
User preferences: {user_prefs}
Audio analysis (key, bpm, chords): {analysis_data}

Complete the StyleProfile JSON below. Be precise and historically accurate.
For every instrument, specify its exact cultural role and playing technique.
For ornaments, use their traditional names (e.g. krekhts, glissando, appoggiatura).
For rhythm patterns, describe the actual beat subdivisions.

Return ONLY a complete StyleProfile JSON object with these fields:
{{
  "genre": "string",
  "era": "string",
  "subStyle": "string",
  "region": "string",
  "scaleType": "string",
  "chordVocabulary": ["i", "iv", "V7"],
  "progressionPatterns": [["i", "iv", "V7", "i"]],
  "modulationTendency": "frequent|rare|none",
  "timeSignature": "4/4",
  "bpmRange": [80, 120],
  "rhythmPattern": "string",
  "swingFactor": 0.0,
  "grooveTemplate": "laid_back|on_top|pushed",
  "instruments": [
    {{
      "name": "string",
      "role": "MELODY_LEAD|MELODY_COUNTER|HARMONY_CHORD|HARMONY_PAD|BASS|RHYTHM_KICK|RHYTHM_SNARE|RHYTHM_PERC|COLOR|DRONE",
      "midiProgram": 0,
      "volumeWeight": 0.8,
      "panPosition": 0.0,
      "playingStyle": "legato",
      "patternRef": "string"
    }}
  ],
  "voicingStyle": "open|close|spread",
  "textureType": "sparse|dense|layered",
  "sectionLabels": ["Intro", "Verse", "Chorus"],
  "formTemplate": "string",
  "repeatStyle": "none|with_variation|exact",
  "ornamentStyle": "string",
  "dynamicsProfile": "string",
  "reverbRoom": "dry|chamber|hall",
  "humanizationLevel": 0.7
}}
"""

CLARIFICATION_QUESTIONS = [
    "איזה סגנון מוזיקה אתה מחפש? (למשל: קלזמר, פלמנקו, בוסה נובה, מזרחי, ג'אז)",
    "מתי? שנות ה-30? עכשווי? מסורתי? (תקופה משפיעה על הסאונד מאוד)",
    "מאיזה אזור בעולם? (מזרח אירופה, ברזיל, ספרד, מזרח תיכון?)",
    "איזו תחושה/אנרגיה אתה רוצה? (חגיגי, אינטימי, אנרגטי, עצוב, שמח?)",
    "יש כלים ספציפיים שחייבים להיות בעיבוד? (קלרינט, עוד, אקורדיון, גיטרה?)",
    "יש אמן או יצירה שנשמעת כמו שאתה רוצה? (לדוגמה: David Broza, Fairuz, Piazzolla)",
]
