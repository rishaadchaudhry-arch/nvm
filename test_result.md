#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
## Local accounts (2026-11-10)
- Backend: POST /api/admin/local-accounts (multipart, admin JWT; fields place_key, era, body, told_by, village, collected_on YYYY-MM-DD, optional photo image <8MB stored in Emergent Object Storage), GET /api/local-accounts?place_key=, GET /api/local-accounts/{id}/photo (public), GET /api/admin/local-accounts, DELETE /api/admin/local-accounts/{id} (soft delete)
- Frontend: admin.tsx segmented "Stories | Local accounts" (form in src/components/local-account-form.tsx with street search → api.look → place key, era chips, text, told by, village, date, photo picker); place/[key].tsx shows LocalAccountCard inside the matching era node with legend; timeline now renders when a place has no written records but has local accounts
- Admin: admin@yatra.app / Yatra-a20d244dfc16. Seeded sample account exists on place lajpat-nagar-ii-1a9b6fe7 (era 1900_1947, with photo)
- agent_communication: main agent verified backend create+photo round trip via curl and a web screenshot of the timeline; needs testing agent for admin UI flow + regressions (stories queue unchanged)

## Bulk import / export (2026-11-11)
- POST /api/admin/local-accounts/import (admin, multipart 'file' CSV; columns street|place_key, era (key or label e.g. "1900–1947"), story|body, told_by, village, collected_on (YYYY-MM-DD or DD/MM/YYYY); street names geocoded via Nominatim; returns {created, rows, failed[{row,street,reason}], created_rows}; good rows saved, bad rows reported; max 200 rows / 2 MB)
- GET /api/admin/local-accounts/template.csv (public template), GET /api/admin/export.csv (admin via Bearer header OR ?token=; CSV of all local accounts + community stories with 'type' column)
- Frontend: src/components/bulk-tools.tsx inside admin Local accounts tab: Import CSV (document picker), Template, Download backup (web opens URL with token; native writes file + share sheet)
- Main agent verified backend via curl (partial-failure import, export, 401 without token) and a web screenshot of the panel.

## History editor + Hindi Wikipedia + photo on existing account (2026-11-11)
- history_engine.gather_sources now also pulls Hindi Wikipedia (geosearch, interlanguage links of English hits, direct hi search for narrow levels); sources carry lang ("en"/"hi"); prompt tells the LLM to translate Hindi facts and cite them. Citation rule unchanged (uncited text dropped).
- PUT /api/admin/history/{key} (HistoryEdit: summary, then_now, eras[{key,heading,text,scope,sources}], new_sources[{title,url,scope}]) — 422 if any era has text without a citable source, or scope invalid; manual sources appended with type "manual"; sets edited_at/edited_by. POST /api/admin/history/{key}/rebuild — deletes and rebuilds from fresh sources, returns History.
- POST /api/admin/local-accounts/{id}/photo (multipart 'photo') attaches/replaces a photo on an existing account.
- Frontend: admin third tab "History" (src/components/history-editor.tsx): street picker → summary/then-now, source list, add new source, per-era heading/text/scope chips/source toggles, Save (disabled while an era has text but no source), Rebuild with tap-again confirm. AccountRow has "Add photo / Replace photo". Sources on place page show "Wikipedia (Hindi)" / "Added by the NVM team".
- Note: Nai Sarak (nai-sarak-1017b307) pre1500 era currently contains a test hand-edit with manual source [16]; testing may rebuild it.

## Share card (2026-11-11)
- GET /api/history/{key}/card-facts → [{label,text}] (404 if no records); GET /api/history/{key}/card.png?fact=N → 1080x1350 PNG rendered with Pillow (backend/share_card.py, fonts in backend/fonts, cached in backend/card_cache), fact index wraps modulo count; 404 if no records.
- Frontend: share-btn in place/[key] header (only when has_records) opens ShareCardModal (src/components/share-card.tsx): preview image, "Fact i of n", Another fact (cycles), Share (web: opens PNG in new tab; native: downloads to cache + expo-sharing sheet).

## OpenAI key switch (2026-11-11)
- backend/openai_voice.py: generate_text (gpt-6-sol, Responses API) and synthesize_mp3 (gpt-realtime-2.1-mini via client.realtime.connect, PCM24k → MP3 via lameenc). history_engine.compose_history and server.narrate now use OPENAI_API_KEY; emergentintegrations no longer imported. openai upgraded to 3.49.0.
- Verified: key authenticates; both text and realtime calls currently return insufficient_quota (user's OpenAI account has no credits) → surfaced as a clear 502 message via openai_error_detail. Cached histories, cards, local accounts, stories unaffected. Live generation to be re-verified once the user adds OpenAI credits.
