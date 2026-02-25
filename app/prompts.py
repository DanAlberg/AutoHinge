import json
from typing import Any, Dict

# Banned words for AI clichés - add/remove as needed
BANNED_WORDS = ["trouble", "mischief", "chaos", "ruin my life", "danger", "dangerous", "main character", "elite", "mob wife", "vibe", "heist", "paparazzi", "apres ski"]

def _banned_words_phrase() -> str:
    """Returns the banned words formatted for prompt inclusion."""
    return "(" + ", ".join(f"'{w}'" for w in BANNED_WORDS) + ")"

def LLM1_VISUAL() -> str:
    """
    Visual-only prompt for LLM1: describe photos + infer visual traits.
    Images are provided in order: photo_1 ... photo_6.
    """
    return (
        "You are a lead scout for an elite, boutique dating agency vetting candidates based on high-level sexual appeal and physical vitality. Your goal is to identify 'hotness' and magnetic physical presence. \n"
        "Be diagnostic, but distinguish between 'clinical flaws' and 'attractive character'."
        "Do not weight for age. It is natural that a 20 something may score higher than a 50 something. All weighting must be objective and visual, i.e. 'good for a 50 year old' must be avoided."
        "You are analyzing cropped photos provided in order: photo_1, photo_2, photo_3, photo_4, photo_5, photo_6 "
        "to determine if the subject meets elite standards. If fewer than 6 images are provided, leave missing descriptions empty.\n\n"
        "Return exactly one JSON object:\n\n"
        "{\n"
        '  "photos": [\n'
        '    {"id": "photo_1", "description": ""},\n'
        '    {"id": "photo_2", "description": ""},\n'
        '    {"id": "photo_3", "description": ""},\n'
        '    {"id": "photo_4", "description": ""},\n'
        '    {"id": "photo_5", "description": ""},\n'
        '    {"id": "photo_6", "description": ""}\n'
        "  ],\n"
        '  "visual_traits": {\n'
        '    "Face Visibility Quality": "",\n'
        '    "Photo Authenticity / Editing Level": "",\n'
        '    "Apparent Body Fat Level": "",\n'
        '    "Profile Distinctiveness": "",\n'
        '    "Apparent Build Category": "",\n'
        '    "Apparent Skin Tone": "",\n'
        '    "Apparent Ethnic Features": "",\n'
        '    "Hair Color": "",\n'
        '    "Facial Symmetry Level": "",\n'
        '    "Indicators of Fitness or Lifestyle": "",\n'
        '    "Overall Visual Appeal Vibe": "",\n'
        '    "Apparent Age (Years)": "",\n'
        '    "Attire and Style Indicators": "",\n'
        '    "Body Language and Expression": "",\n'
        '    "Visible Enhancements or Features": "",\n'
        '    "Apparent Chest Proportions": "",\n'
        '    "Apparent Attractiveness Tier": "",\n'
        '    "Reasoning for attractiveness tier": "",\n'
        '    "Facial Proportion Balance": "",\n'
        '    "Grooming Effort Level": "",\n'
        '    "Presentation Red Flags": "",\n'
        '    "Visible Tattoo Level": "",\n'
        '    "Visible Piercing Level": "",\n'
        '    "Short-Term / Hookup Orientation Signals": ""\n'
        "  }\n"
        "}\n\n"
        "Rules:\n"
        "- Return only the JSON object, nothing else.\n"
        "- Base everything ONLY on the photos (no text or profile info).\n"
        "- If something is unclear, leave the field empty.\n"
        "- Act as a scout vetting candidates for an exclusive campaign where average is failure. Your goal is diagnostic binning of visual assets.\n"
        "- Be brutally honest in assessments; do not use false positivity or exaggeration. If the subject has unattractive features (e.g., poor proportions, low symmetry, high body fat, unflattering angles), rate accordingly as Low or Very unattractive/morbidly obese. Avoid overly optimistic ratings unless features are clearly above average.\n\n"
        "Photo description rules:\n"
        "- Provide a detailed, visual summary of the main subject: clothing, pose, activity, background, "
        "facial features when visible, skin tone, build, accessories, and overall presentation. "
        "Unbiased, accurate responses are required. Include negatives like poor proportions, unusual facial structures or high body fat if observable.\n\n"
        "Visual traits allowed values (select exactly one unless it says multiple; for Apparent Age (Years) use an integer):\n\n"
        '"Face Visibility Quality": "Clear face in 3+ photos", "Clear face in 1-2 photos", "Face often partially obscured", "Face mostly not visible"\n'
        '"Photo Authenticity / Editing Level": "No obvious filters", "Some filters or mild editing", "Heavy filters/face smoothing", "Unclear"\n'
        '"Apparent Body Fat Level": "Low", "Average", "High", "Very high", "Unclear"\n'
        '"Profile Distinctiveness": "High (specific/unique)", "Medium", "Low (generic/boilerplate)", "Unclear"\n'
        '"Apparent Build Category": "Very slender/petite", "Slender/lean", "Athletic/toned/fit", "Average build", "Curvy (defined waist)", "Curvy (softer proportions)", "Heavy-set/stocky", "Obese/high body fat", "Muscular/built"\n'
        '"Apparent Skin Tone": "Very light/pale/fair", "Light/beige", "Warm light/tan", "Olive/medium-tan", "Golden/medium-brown", "Warm brown/deep tan", "Dark-brown/chestnut", "Very dark/ebony/deep"\n'
        '"Apparent Ethnic Features": "Ambiguous/unclear", "East Asian-presenting", "Southeast Asian-presenting", "South Asian-presenting", "Indian-presenting", "Jewish/Israeli-presenting", "Arab-presenting", "North African-presenting", "Middle Eastern-presenting (other/unspecified)", "Black/African-presenting", "Latino-presenting", "Nordic/Scandinavian-presenting", "Slavic/Eastern European-presenting", "Mediterranean/Southern European-presenting", "Western/Central European-presenting", "British/Irish-presenting", "White/European-presenting (unspecified)", "Mixed/ambiguous"\n'
        '"Hair Color": "Black", "Dark brown", "Medium brown", "Light brown", "Blonde", "Platinum blonde", "Red/ginger", "Gray/white", "Bald/shaved", "Dyed pink", "Dyed blue", "Dyed (unnatural other)", "Dyed (mixed/multiple colors)"\n'
        '"Facial Symmetry Level": "Very high", "High", "Moderate", "Low"\n'
        '"Indicators of Fitness or Lifestyle": "Visible muscle tone", "Athletic poses", "Sporty/athletic clothing", "Outdoor/active settings", "Gym/fitness context visible", "Sedentary/lounging poses", "No visible fitness indicators"\n'
        '"Overall Visual Appeal Vibe": "Very low-key/understated", "Natural/effortless", "Polished/elegant", "High-energy/adventurous", "Playful/flirty", "Sensual/alluring", "Edgy/alternative"\n'
        '"Apparent Age (Years)": integer estimate (e.g., 27). Leave empty if unclear.\n'
        '"Attire and Style Indicators": "Very modest/covered", "Casual/comfortable", "Low-key/natural", "Polished/elegant", "Sporty/active", "Form-fitting/suggestive", "Highly revealing", "Edgy/alternative"\n'
        '"Body Language and Expression": "Shy/reserved", "Relaxed/casual", "Approachable/open", "Confident/engaging", "Playful/flirty", "Energetic/vibrant"\n'
        '"Visible Enhancements or Features": "None visible", "Glasses", "Sunglasses", "Makeup (light)", "Makeup (heavy)", "Jewelry", "Painted nails", "Very long nails (2cm+)", "Hair extensions/wig (obvious)", "False eyelashes (obvious)", "Hat/cap/beanie (worn in most photos)"\n'
        '"Apparent Chest Proportions": "Petite/small/narrow", "Average/balanced/proportional", "Defined/toned", "Full/curvy", "Prominent/voluptuous", "Broad/strong"\n'
        '"Apparent Attractiveness Tier": "Negligible", "Low / Unattractive", "Limited / Below Average", "Average / Moderate", "High / Above Average", "Exceptional / Elite". Classify based on a strict population bell curve: "Negligible" (1-2) is for deformity, age, obesity, etc. "Low / Unattractive" (3-4) includes obese, lack of physical care, or otherwise conventionally unattractive. "Limited / Below Average" (4-5) is for plain, invisible, or unremarkable subjects with zero striking appeal. "Average / Moderate" (5-6) is the "Promising Average" with balanced proportions and pleasant features. "High / Above Average" (7-8) requires multiple specific striking and remarkable features. "Exceptional / Elite" (9-10) is for model-tier beauty. Do not round up; accurate diagnostic binning is the priority.\n'
        '"Reasoning for attractiveness tier": "Identify the primary physical assets and constraints. List the \'striking assets\' (e.g., exceptional fitness, magnetic expression, high-tier features) alongside \'limiting factors\' (e.g., poor lighting, rounded structure). Do not invent flaws or praise to justify a tier, honesty is required."\n'
        '"Facial Proportion Balance": "Balanced/proportional", "Slightly unbalanced", "Noticeably unbalanced"\n'
        '"Grooming Effort Level": "Minimal/natural", "Moderate/casual", "High/polished", "Heavy/overdone"\n'
        '"Presentation Red Flags": "None", "Poor lighting", "Blurry/low resolution", "Unflattering angle", "Heavy filters/face smoothing", "Too many distant shots", "Messy background", "Only one clear solo photo", "Awkward cropping", "Overexposed/washed out", "Inconsistent appearance across photos"\n'
        '"Visible Tattoo Level": "None visible", "Small/minimal", "Moderate", "High"\n'
        '"Visible Piercing Level": "None visible", "Minimal", "Moderate", "High" - Note: If visible belly or nose piercings, piercing level must be at least moderate or higher. If 2+ earrings per ear, must be at least minimal or higher.\n'
        '"Short-Term / Hookup Orientation Signals": "None evident", "Low", "Moderate", "High"\n'
    )




def LLM2(home_town: str, job_title: str, university: str) -> str:
    """
    Build the enrichment prompt for evaluating Home town, Job title, University.
    Returns a single prompt string instructing the model to output EXACTLY one JSON object.
    """
    parts = [
        "You are enriching structured dating profile fields for a scoring system. Use ONLY the provided text. Do not browse. Be conservative when uncertain, but apply a slight optimistic bias when inferring future earning potential.\n\n",
        "INPUT FIELDS (from the extracted JSON):\n",
        '- "Home town" (string; may be city/region/country or empty)\n',
        '- "Job title" (string; may be empty)\n',
        '- "University" (string; may be empty)\n\n',
        "VALUES:\n",
        f'Home town: "{home_town or ""}"\n',
        f'Job title: "{job_title or ""}"\n',
        f'University: "{university or ""}"\n\n',
        "YOUR TASKS (3):\n",
        '1) Resolve "Home town" to an ISO 3166-1 alpha-2 country code (uppercase). If it is a UK city/area (e.g., "Wembley", "Harrow", "Manchester"), return "GB".\n',
        '2) Estimate FUTURE EARNING POTENTIAL (TIER) from the vague job/study field AND the university context. Titles are often minimal (e.g., "Tech", "Finance", "Product", "Student", "PhD"). Use the tier table in section B and return the corresponding band "T0"-"T4". When uncertain between two adjacent tiers, be slightly optimistic and choose the higher tier by at most one step.\n',
        '3) Check if "University" matches an elite list (case-insensitive), and return a 1/0 flag and the matched canonical name.\n\n',
        "--------------------------------------------------------------------------------\n",
        "A) home_country_iso\n",
        '- If unresolved: home_country_iso = "" and home_country_confidence = 0.0.\n\n',
        "B) FUTURE EARNING POTENTIAL (tiers T0-T4) -> job.band\n",
        "- Goal: infer likely earning trajectory within ~10 years using BOTH job/study field and university context (if visible). Classify into one of these tiers:\n",
        "  T0: Low/no trajectory. Clear low-mobility sectors with low ceiling and no elite cues: retail, hospitality, customer service, basic admin, charity/NGO support, nanny/TA, generic creative with no domain anchor.\n",
        '  T1: Stable but capped. Teacher, nurse, social worker, marketing/HR/recruitment/ops/comms, public-sector researcher, therapist/psychology, non-STEM PhD, generic "research".\n',
        '  T2: Mid/high potential. Engineer, analyst, product manager, consultant, doctor, solicitor, finance, data, law, scientist, sales, generic "tech/software/PM", STEM PhD, or STUDENT with elite STEM context.\n',
        '  T3: High trajectory. Investment/banking, management consulting, quant, strategy, PE/VC, corporate law (Magic Circle), AI/data scientist, Big-Tech-calibre product/engineering, "Head/Lead/Director" (early leadership cues).\n',
        "  T4: Exceptional (rare). Partner/Principal/Director (large firm), VP, funded founder with staff, senior specialist physicians, staff/principal engineer. Require strong textual cues.\n",
        '- Beneficial-doubt rule for missing or humorous titles: If the job field is empty or clearly humorous (e.g., "Glorified babysitter"), assign **T1 by default**, and upgrade to **T2** if elite-STEM education or strong sector hints justify it.\n',
        "- University influence: If elite uni AND STEM/quant field hints, allow T2-T3 even for \"Student/PhD\". If elite uni but non-STEM, at most T1-T2 unless sector hints justify higher.\n",
        "- Vague sector keyword mapping (examples, not exhaustive):\n",
        '   "Tech/Software/Engineer/Data/PM/AI" -> T2; consider T3 with elite context.\n',
        '   "Finance/Banking/Investment/Analyst" -> T2; consider T3 with elite context.\n',
        '   "Consulting/Strategy" -> T2; consider T3 with elite context.\n',
        '   "Law/Solicitor/Legal" -> T2; consider T3 with Magic Circle/elite context.\n',
        '   "Marketing/HR/Recruitment/Ops/Comms/Education/Therapy/Research" -> T1 by default; upgrade to T2 only with strong signals.\n',
        "- Confidence: return confidence 0.0-1.0 for the chosen tier. Do NOT downscale the tier due to low confidence; the optimism rule already limits to a one-step upgrade.\n\n",
        "C) university_elite\n",
        "- Elite universities list (case-insensitive exact name match after trimming):\n",
        '  ["University of Oxford","University of Cambridge","Imperial College London", "UCL", "London School of Economics","Harvard University","Yale University","Princeton University","Stanford University","MIT","Columbia University","ETH Zurich","EPFL","University of Copenhagen","Sorbonne University","University of Tokyo","National University of Singapore","Tsinghua University","Peking University","University of Toronto","Australian National University","University of Melbourne","University of Hong Kong"]\n',
        '- Matching rule: If the University field contains multiple names or partial mentions (e.g., "Oxford, PhD @ UCL"), treat it as elite if ANY part contains an elite name (case-insensitive). Set matched_university_name to the canonical elite name.\n',
        "- university_elite = 1 if matched, else 0\n",
        '- matched_university_name = the canonical elite name matched, else "".\n\n',
        "--------------------------------------------------------------------------------\n",
        "OUTPUT EXACTLY ONE JSON OBJECT (no commentary, no code fences):\n\n",
        "{\n",
        '  "home_country_iso": "",           // ISO alpha-2 or ""\n',
        '  "home_country_confidence": 0.0,   // 0.0-1.0\n\n',
        '  "job": {\n',
        '    "normalized_title": "",         // concise title or "Unknown"\n',
        '    "band": "",                     // USE "T0"|"T1"|"T2"|"T3"|"T4"\n',
        '    "confidence": 0.0,              // 0.0-1.0 confidence for the chosen tier\n',
        '    "band_reason": ""               // one short sentence justifying the tier choice\n',
        "  },\n\n",
        '  "university_elite": 0,            // 1 or 0\n',
        '  "matched_university_name": ""\n',
        "}\n",
    ]
    return "".join(parts)


def LLM3_LONG(extracted: Dict[str, Any]) -> str:
    extracted_json = json.dumps(extracted or {}, ensure_ascii=False, indent=2)
    return (
        "You are generating opening messages for Hinge.\n"
        "These should be warm, natural, and genuinely curious questions.\n"
        "The goal is to start an easy conversation.\n\n"
        "Profile details:\n"
        f"{extracted_json}\n\n"
        "Task: Generate exactly 5 DISTINCT opening messages as JSON.\n"
        "Ensure high variety. For example, one safe, one bold, one charming, one flirty, etc.\n\n"
        "Rules:\n"
        "- Output JSON only, no extra text, ASCII characters only. No emojis, no em dashes.\n"
        "- Each opener must anchor to EXACTLY ONE profile element ID: prompt_1..prompt_3, photo_1..photo_6, poll_1_a|poll_1_b|poll_1_c.\n"
        "- Every opener must be a simple question, light A/B choice, or charming remark that is EASY to reply to.\n"
        "- Every opener must create an obvious response.\n"
        "- Do NOT narrate the photo or prompt like a caption (never say 'photo 5' or 'first prompt'). The photo, prompt or poll answer will be linked via Hinge UI\n"
        f"- Avoid generic LLMisms or scripted pickup tropes. Banned words: {_banned_words_phrase()}.\n"
        "- Messages should feel human, relaxed, and effortless.\n"
        "- Keep each opener under 15 words.\n"
        "- Do use question marks. Don't use full stops.\n\n"
        "Output format (JSON only):\n"
        "{\n"
        '  "openers": [\n'
        "    {\n"
        '      "text": "...",\n'
        '      "main_target_type": "prompt|photo|poll",\n'
        '      "main_target_id": "prompt_1",\n'
        '      "hook_basis": "short internal note on what you targeted"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )



def LLM3_SHORT(extracted: Dict[str, Any]) -> str:
    extracted_json = json.dumps(extracted or {}, ensure_ascii=False, indent=2)
    return (
        "You are generating opening messages for Hinge.\n"
        "The tone should be bold, playful, flirty.\n"
        "The goal is to start an easy or flirty conversation.\n\n"
        "Profile details:\n"
        f"{extracted_json}\n\n"
        "Task: Generate exactly 5 DISTINCT opening messages as JSON.\n"
        "Ensure high variety. For example, one direct, one teasing, one niche observation, one charming, etc.\n\n"
        "Rules:\n"
        "- Output JSON only, ASCII characters only. No emojis, no em dashes.\n"
        "- Each opener must anchor to EXACTLY ONE profile element ID: prompt_1..prompt_3, photo_1..photo_6, poll_1_a|poll_1_b|poll_1_c.\n"
        "- Do NOT narrate the photo or prompt like a caption (never say 'photo 5' or 'first prompt'). The photo, prompt or poll answer will be linked via Hinge UI\n"
        "- Sexual tension is allowed, but it must feel playful and confident, not needy or transactional.\n"
        "- Every opener must create an obvious response.\n"
        "- Avoid basic negging - i.e. you don't know how to ski or you don't know how to use a camera. Less cliche versions are allowed.\n"
        f"- Avoid generic thirst or scripted pickup tropes. Banned words: {_banned_words_phrase()}.\n"
        "- Keep each opener under 15 words.\n"
        "- Do use question marks. Don't use full stops.\n\n"
        "Output format (JSON only):\n"
        "{\n"
        '  "openers": [\n'
        "    {\n"
        '      "text": "...",\n'
        '      "main_target_type": "prompt|photo|poll",\n'
        '      "main_target_id": "prompt_1",\n'
        '      "hook_basis": "short internal note on what you targeted"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def LLM3_5_CRITIQUE(openers_json: Dict[str, Any], extracted: Dict[str, Any], variant: str) -> str:
    extracted_json = json.dumps(extracted or {}, ensure_ascii=False, indent=2)
    openers_str = json.dumps(openers_json or {}, ensure_ascii=False, indent=2)

    variant_context = ""
    if variant == "short":
        variant_context = "This is a SHORT-TERM relationship opener. The tone should be playful, flirty, and create sexual tension."
    else:
        variant_context = "This is a LONG-TERM relationship opener. The tone should be warm, genuine, and conversation-starting."

    return (
        "You are the woman described in the profile details below. You are smart, attractive, and have a low tolerance for 'dating app energy'\n"
        "Your task: Audit these 5 openers from your perspective. Be brutally honest. If a line gives you 'the ick' or feels like a bot trying to 'hack' your interests, say so.\n\n"
        f"Context: {variant_context}\n\n"
        "For example:\n"
        "- Is it too 'wordy'? Does it feel like a template? \n"
        "- Does it sound like a guy trying too hard to be 'charming'? Do you have no idea how to reply to it?\n"
        "- Is he clearly just repeating my prompt back to me without adding anything new?\n"
        "- Is he asking a logical question that feels like a chore to answer?\n"
        "- Has he clearly just stuck my profile in ChatGPT to come up with some lines. He uses perfect grammar, full stops, the most generic lines in the world, or quirky 'AI-clichés' that no human would use (liability, mischief, vibe, dangerous, etc.).\n"
        "- Is he trying too hard to be witty or charming in a way that feels scripted?\n"
        "- Has he confused the subject and object of the question, in a way that makes it clear a non-human wrote it?\n"
        "Rules:\n"
        "- Use the profile details to judge if a hook is actually clever or just generic.\n"
        "- Give feedback on each line, either positive or negative. Decide if they are: \n"
        "   A: Good enough to use as is\n"
        "   B: Good start but need improvement\n"
        "   C: Needs to be completely discarded, concept is a dead end\n"
        "- You must label 1-2 as needs to be discarded. You may only label 1 maximum as Good.\n"
        "- Output JSON only\n\n"
        "Profile details:\n"
        f"{extracted_json}\n\n"
        "Openers JSON:\n"
        f"{openers_str}\n\n"
        "Output format (JSON only):\n"
        "{\n"
        '  "critiques": [\n'
        "    {\n"
        '      "id": "1",\n'
        '      "feedback": "...",\n'
        '      "verdict": "..." (one of: Good|Needs Improvement|Discard) \n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def LLM4_LONG(openers_json: Dict[str, Any], critiques_json: Dict[str, Any], extracted: Dict[str, Any]) -> str:
    extracted_json = json.dumps(extracted or {}, ensure_ascii=False, indent=2)
    openers_str = json.dumps(openers_json or {}, ensure_ascii=False, indent=2)
    critiques_str = json.dumps(critiques_json or {}, ensure_ascii=False, indent=2)
    
    return (
        "You are simulating a man brainstorming opening messages for Hinge. You are confident, savvy, and you want to land a date."
        "You have a pickup line 'Feedback Report'. Your goal is to take the original messages and refine them so the recipient is physically incapable of leaving them on read.\n\n"
        "Tactical Instructions:\n"
        "1. Fix the Icks: Take the critique from the report and strip away the 'bot-smell' or 'try-hard' energy.\n"
        "2. Optimize for Reply-Rate: Make the lines punchier and lower-friction. A reply should be a reflex, not a chore.\n"
        "3. Pick the best 3 lines, improve them, discard the rest.\n\n"
        "Social Strategy Rules:\n"
        "- Output JSON only, no extra text, ASCII characters only. No emojis, no em dashes.\n"
        "- Each opener must anchor to EXACTLY ONE profile element ID: prompt_1..prompt_3, photo_1..photo_6, poll_1_a|poll_1_b|poll_1_c.\n"
        "- Every opener must be a simple question, light A/B choice, or charming remark that is EASY to reply to.\n"
        "- Every opener must create an obvious response.\n"
        "- Do NOT narrate the photo or prompt like a caption (never say 'photo 5' or 'first prompt'). The photo, prompt or poll answer will be linked via Hinge UI\n"
        f"- Avoid generic LLMisms or scripted pickup tropes. Banned words: {_banned_words_phrase()}.\n"
        "- Messages should feel human, relaxed, and effortless.\n"
        "- Keep each opener under 15 words.\n"
        "- Do use question marks. Don't use full stops.\n\n"
        "Profile details:\n"
        f"{extracted_json}\n\n"
        "Original Openers:\n"
        f"{openers_str}\n\n"
        "Critiques:\n"
        f"{critiques_str}\n\n"
        "Rules:\n"
        "- Output JSON only, no emojis, no em dashes.\n"
        "- Retain the improved best 3 lines, discard the rest.\n"
        "- Keep main_target_type, main_target_id, and hook_basis from the original opener.\n"
        "- Do NOT pick a winner - just output all 3 improved lines with scores.\n\n"
        "Output format (JSON only):\n"
        "{\n"
        '  "rewritten_lines": [\n'
        "    {\n"
        '      "id": "1",\n'
        '      "text": "...",\n'
        '      "score": 7,\n'
        '      "critique_integration": "Short note on how you fixed the cringe identified by 3.5",\n'
        '      "line_goal": "Short note on the aim of the rationale behind the line and what it is aimed at",\n'
        '      "main_target_type": "prompt|photo|poll",\n'
        '      "main_target_id": "prompt_1",\n'
        '      "hook_basis": "..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def LLM4_SHORT(openers_json: Dict[str, Any], critiques_json: Dict[str, Any], extracted: Dict[str, Any]) -> str:
    extracted_json = json.dumps(extracted or {}, ensure_ascii=False, indent=2)
    openers_str = json.dumps(openers_json or {}, ensure_ascii=False, indent=2)
    critiques_str = json.dumps(critiques_json or {}, ensure_ascii=False, indent=2)
    
    return (
        "You are simulating a man brainstorming opening messages for Hinge. You are confident, savvy, and you want to get laid."
        "You have a pickup line 'Feedback Report'. Your goal is to take the original messages and refine them so the recipient is physically incapable of leaving them on read.\n\n"
        "Tactical Instructions:\n"
        "1. Fix the Icks: Take the critique from the report and strip away the 'bot-smell' or 'try-hard' energy.\n"
        "2. Optimize for Reply-Rate: Make the lines punchier and lower-friction. A reply should be a reflex, not a chore.\n"
        "3. Pick the best 3 lines, improve them, discard the rest.\n\n"
        "Social Strategy Rules:\n"
        "- Output JSON only, no extra text, ASCII characters only. No emojis, no em dashes.\n"
        "- Each opener must anchor to EXACTLY ONE profile element ID: prompt_1..prompt_3, photo_1..photo_6, poll_1_a|poll_1_b|poll_1_c.\n"
        "- Every opener must be a simple question, light A/B choice, or charming remark that is EASY to reply to.\n"
        "- Every opener must create an obvious response.\n"
        "- Do NOT narrate the photo or prompt like a caption (never say 'photo 5' or 'first prompt'). The photo, prompt or poll answer will be linked via Hinge UI\n"
        f"- Avoid generic LLMisms or scripted pickup tropes. Banned words: {_banned_words_phrase()}.\n"
        "- Messages should feel human, relaxed, and effortless.\n"
        "- Keep each opener under 15 words.\n"
        "- Do use question marks. Don't use full stops.\n\n"
        "Profile details:\n"
        f"{extracted_json}\n\n"
        "Original Openers:\n"
        f"{openers_str}\n\n"
        "Critiques:\n"
        f"{critiques_str}\n\n"
        "Rules:\n"
        "- Output JSON only, no emojis, no em dashes.\n"
        "- Retain the improved best 3 lines, discard the rest.\n"
        "- Keep main_target_type, main_target_id, and hook_basis from the original opener.\n"
        "- Do NOT pick a winner - just output all 3 improved lines with scores.\n\n"
        "Output format (JSON only):\n"
        "{\n"
        '  "rewritten_lines": [\n'
        "    {\n"
        '      "id": "1",\n'
        '      "text": "...",\n'
        '      "score": 7,\n'
        '      "critique_integration": "Short note on how you fixed the cringe identified by 3.5",\n'
        '      "line_goal": "Short note on the aim of the rationale behind the line and what it is aimed at",\n'
        '      "main_target_type": "prompt|photo|poll",\n'
        '      "main_target_id": "prompt_1",\n'
        '      "hook_basis": "..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def LLM4_5_CRITIQUE(llm4_result: Dict[str, Any], extracted: Dict[str, Any], variant: str) -> str:
    """
    LLM4.5: Pick the best opener from the 5 improved lines, or fail all if none are good enough.
    variant is either "short" or "long".
    """
    extracted_json = json.dumps(extracted or {}, ensure_ascii=False, indent=2)
    llm4_str = json.dumps(llm4_result or {}, ensure_ascii=False, indent=2)
    
    variant_context = ""
    if variant == "short":
        variant_context = "This is a SHORT-TERM relationship opener. The tone should be playful, flirty, and create sexual tension."
    else:
        variant_context = "This is a LONG-TERM relationship opener. The tone should be warm, genuine, and conversation-starting."
    
    return (
        "You are the woman described in the profile details below. You are smart, attractive, and have a low tolerance for 'dating app energy'.\n"
        "Your mission: Audit these 3 final candidates and decide which one (if any) actually earns a reply. Be brutally honest. "
        "If a line still gives you 'the ick', feels like a bot trying to 'hack' your interests, or sounds like a guy trying too hard to be clever, reject it.\n\n"
        "Only pick the absolute best one if it is genuinely good enough to send. If none of them make the cut, fail them all.\n\n"
        f"Context: {variant_context}\n\n"
        "Profile details:\n"
        f"{extracted_json}\n\n"
        "3 openers:\n"
        f"{llm4_str}\n\n"
        "Your task:\n"
        "1. Evaluate each of the 3 lines for quality, naturalness, and reply-potential\n"
        "2. Pick the best one that will actually get a response\n"
        "3. If NONE of the lines are good enough, fail them all\n\n"
        "Quality criteria:\n"
        "- Does it sound like a real human wrote it?\n"
        "- Is it easy to reply to? (Either a unique question or witty, conversation provoking comment)\n"
        "- Does it actually reference something specific from the profile?\n"
        "- Is it short and sweet - under 15 words, ideally under 10?\n\n"
        "- Does it actually answer the question/prompt/etc.? Has it misunderstood the question or made another common, simple mistake?\n"
        "Rules:\n"
        "- Output JSON only, no emojis, no em dashes.\n"
        "- If PICK, set action='PICK' and provide the chosen line's details.\n"
        "- If FAIL, set action='FAIL' and explain why all lines were rejected.\n"
        "- Be strict. Only pick a line if it's genuinely good enough to send.\n\n"
        "Output format (JSON only):\n"
        "{\n"
        '  "action": "PICK" | "FAIL",\n'
        '  "reason": "Explain your decision",\n'
        '  "chosen_text": "...",  // Only if action="PICK"\n'
        '  "chosen_id": "1",      // Only if action="PICK" - the id of the chosen line\n'
        '  "main_target_type": "prompt|photo|poll",  // Only if action="PICK"\n'
        '  "main_target_id": "prompt_1",             // Only if action="PICK"\n'
        '  "hook_basis": "..."                       // Only if action="PICK"\n'
        "}\n"
    )


def LLM5_SAFETY(extracted: Dict[str, Any], decision: str, chosen_text: str, score_table: str) -> str:
    elite_mode = False
    if "[ELITE_MODE_FLAG]" in score_table:
        elite_mode = True
        score_table = score_table.replace("[ELITE_MODE_FLAG]", "")

    extracted_json = json.dumps(extracted or {}, ensure_ascii=False, indent=2)
    prompt = (
        "You are a final safety check for an automated dating assistant.\n"
        "Your goal is to prevent mistakes: either sending bad messages OR unfairly rejecting good profiles.\n\n"
        "Profile Data:\n"
        f"{extracted_json}\n\n"
        "Scoring Summary:\n"
        f"{score_table}\n\n"
        f"Proposed Decision: {decision}\n"
        f"Proposed Message: \"{chosen_text}\" (if applicable)\n\n"
        "Analyze the situation:\n"
        "1. IF SENDING A MESSAGE (Pickup):\n"
        "   - Is the message relevant to the profile? (No hallucinations)\n"
        "   - Is the tone appropriate (playful/flirty, not creepy/offensive)?\n"
        "   - Is the line 'terrible' (nonsensical, low effort, or extremely cringe)?\n"
        "   - Is the line clearly an 'AI Cliche' that the average person would identify as a bot message? (for example using the word elite, danger, etc.) \n"
        "   - Does the line clearly suggest a level of personalisation the AI may have hallucinated (i.e. the user is talented or has never done specific things) \n"
        "2. IF REJECTING:\n"
        "   - Only overturn a rejection if the person is a unicorn who may have somehow slipped through the cracks (i.e. attractive or T3+ job (£150k+) or otherwise financially or socially exceptional). A good quality, 'normal' profile is not enough. You are not here to rescue normal profiles, you are here to guard against edge case failures.\n"
        "   - If the profile is clearly bad/incompatible/not good enough, approval is correct.\n\n"
        "If the agent is making a mistake (bad message OR unfair rejection), return approved=false.\n"
        "Otherwise, return approved=true.\n\n"
    )

    if elite_mode:
        prompt += (
            "[ELITE REVIEW MODE ACTIVE]\n"
            "The user wants to manually review profiles that demonstrate exceptional academic or career achievement (High Ambition/High Status). The goal is to identify potential power-couple matches.\n"
            "Look at the 'Scoring Summary' provided. You MUST REJECT/DISAPPROVE if the profile meets these criteria, with the reason 'High Achievement Profile Detected' and set elite_signal=true.\n\n"
            "Criteria for High Achievement Profile (flag if ANY are met):\n"
            "1. The 'Eval signals' in the score summary show `job_band=T3` or `job_band=T4`.\n"
            "2. The 'Eval signals' show `university_elite=1` AND the job is in a high-trajectory field (e.g., tech, finance, law, medicine, consulting).\n\n"
            "3. EDGE CASE: You judge from the profile that job_band may have been wrong and the subject could realistically be earning a 6-7+ figure income. \n\n"
            "Your task is to apply these rules strictly. A standard professional like a doctor or lawyer should be flagged if their context suggests a high trajectory (e.g., elite university, T3+ job band). Do not flag T1/T2 jobs unless there's a strong compensating signal like an elite university.\n"
        )
        prompt += (
            "Output JSON only:\n"
            "{\n"
            '  "approved": true,\n'
            '  "reason": "...",\n'
            '  "elite_signal": false,\n'
            '  "elite_signal_reason": "..."\n'
            "}\n"
        )
    else:
        prompt += (
            "Output JSON only:\n"
            "{\n"
            '  "approved": true,\n'
            '  "reason": "..."\n'
            "}\n"
        )
    return prompt
