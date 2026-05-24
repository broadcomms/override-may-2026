# OVERRIDE Manual Test Plan
**Version**: 1.0  
**Date**: 2026-05-22  
**Purpose**: Pre-demo usability testing and quality assurance

---

## Document Overview

This manual test plan covers all user flows in the OVERRIDE platform from initial access through post-race analysis. Use this document to conduct comprehensive usability testing.

### Test Environment Setup

**Prerequisites**:
```bash
# Start OVERRIDE application
podman-compose up override -d

# Optional: Start with TORCS for live race testing
podman-compose up override torcs -d

# Optional: Start with TTM forecasting
podman-compose up override ttm -d

# Access application
http://localhost:8000
```

**Test Data Requirements**:
- Sample replay files (available in UI)
- TORCS telemetry captures (if testing live features)
- Multiple sessions for comparison testing

---

## Test Execution Guidelines

### Severity Levels
- **Critical**: Blocks core functionality, prevents task completion
- **High**: Major usability issue, workaround exists
- **Medium**: Minor usability issue, cosmetic problem
- **Low**: Enhancement suggestion, edge case

### Test Result Codes
- ✅ **PASS**: Feature works as expected
- ❌ **FAIL**: Feature does not work, blocks testing
- ⚠️ **PARTIAL**: Feature works with issues
- ⏭️ **SKIP**: Test not applicable to current configuration

### Recording Results
For each test case, record:
1. Test ID
2. Result (PASS/FAIL/PARTIAL/SKIP)
3. Notes (any observations, issues, or suggestions)
4. Screenshots (if applicable)
5. Timestamp

---

## Phase 1: Initial Access & Navigation

### TC-001: Application Launch
**Objective**: Verify application starts and loads correctly

**Steps**:
1. Start application with `podman-compose up override`
2. Wait for startup completion
3. Navigate to `http://localhost:8000`
4. Verify page loads without errors

**Expected Results**:
- Application loads within 10 seconds
- No console errors in browser DevTools
- Header displays "OVERRIDE" branding
- Subheader shows "Explainable AI race-strategy copilot · grounded in FIA · IBM watsonx.ai"
- Version chip appears in header (may load lazily)
- Footer displays Apache 2.0 license and IBM SkillsBuild framing

**Test Data**: None required

**Priority**: Critical

---

### TC-002: Root Redirect
**Objective**: Verify root path redirects to upload page

**Steps**:
1. Navigate to `http://localhost:8000/`
2. Observe URL change

**Expected Results**:
- URL automatically changes to `/upload`
- Upload page content displays

**Test Data**: None required

**Priority**: High

---

### TC-003: Primary Navigation
**Objective**: Verify all navigation links work correctly

**Steps**:
1. From any page, click "Upload" in header navigation
2. Verify Upload page loads
3. Click "Sessions" in header navigation
4. Verify Sessions page loads
5. If TORCS available, click "Driver Lab" in header navigation
6. Verify Driver Lab page loads

**Expected Results**:
- All navigation links are clickable
- Each page loads without errors
- Active page is visually indicated in navigation
- URL updates correctly for each page

**Test Data**: None required

**Priority**: Critical

---

### TC-004: Skip to Content (Accessibility)
**Objective**: Verify keyboard accessibility feature

**Steps**:
1. Load any page
2. Press Tab key once
3. Observe "Skip to content" link appears
4. Press Enter
5. Verify focus moves to main content area

**Expected Results**:
- "Skip to content" link appears on first Tab press
- Link is visually styled (orange background)
- Pressing Enter moves focus to `#main-content`
- Subsequent Tab presses navigate through page content

**Test Data**: None required

**Priority**: Medium

---

### TC-005: Version Information
**Objective**: Verify version chip displays build metadata

**Steps**:
1. Load any page
2. Locate version chip in header (top-right area)
3. Observe version information

**Expected Results**:
- Version chip displays (may load lazily)
- Shows build version or commit hash
- Chip is styled consistently with design system

**Test Data**: None required

**Priority**: Low

---

## Phase 2: Upload & Session Creation (Before Race)

### TC-006: Upload Page Layout
**Objective**: Verify upload page displays all sections correctly

**Steps**:
1. Navigate to `/upload`
2. Observe page layout

**Expected Results**:
- **Left lane**: Sample replays section visible
- **Left lane**: File upload section visible
- **Right lane**: Race control card visible (if TORCS available)
- **Right lane**: Live captures list visible (if TORCS available)
- **Below fold**: Preview strip with cached TORCS fixture
- All sections render without layout issues

**Test Data**: None required

**Priority**: High

---

### TC-007: Sample Replay Demo (Fixture Mode)
**Objective**: Verify sample replay demos load instantly from cached fixtures

**Steps**:
1. Navigate to `/upload`
2. Locate "BEGIN" section with demo fixture cards
3. Observe available demos:
   - **TORCS engineer demo** (RECOMMENDED badge) - 12 laps, 1 zone
   - **Forecast strategy demo** - 35 laps, 1 zone
   - **Layered-defense demo** - 47 laps, 3 zones
   - **Engineer happy-path demo** - 18 laps, 2 zones
4. Click any demo card (e.g., "TORCS engineer demo")
5. Verify immediate navigation to session detail page

**Expected Results**:
- Demo cards are clickable (entire card is interactive, no separate "Analyze" button)
- Navigation is **instant** (no loading indicator - these use cached session artifacts)
- Session detail page displays immediately with complete analysis
- URL shows `?fixture=1` parameter indicating fixture mode
- All session data is pre-populated (zones, recommendations, charts)
- No pipeline processing occurs (fixtures bypass backend)
- No errors in console

**Test Data**: Built-in demo fixtures (cached session artifacts)

**Priority**: Critical

**Note**: Demo fixtures use cached session artifacts so you can explore the UI instantly. Uploading your own file or ingesting a live TORCS capture runs the real backend pipeline.

---

### TC-008: File Upload (Bring Your Own)
**Objective**: Verify custom file upload triggers real backend pipeline

**Steps**:
1. Navigate to `/upload`
2. Locate "BRING YOUR OWN" section below demo fixtures
3. Observe dropzone text: "Drop in a replay session, or click to browse"
4. Verify supported formats shown: "Supports TORCS .json / FastF1 .parquet"
5. Verify upload limit shown: "Upload to 25 MB"
6. Click dropzone or drag-and-drop a valid file [data/samples/laps.parquet](../data/samples/laps.parquet)
7. Observe "Parsing session…" loading state with progress bar
8. Verify loading message: "Reasoning over zones · running safety review · this can take ~30 s"
9. Wait for pipeline completion (~30 seconds)
10. Verify redirect to session detail page

**Expected Results**:
- Dropzone shows clear instructions and format support
- Loading indicator appears immediately on file selection
- Progress bar animates during processing
- Real backend pipeline executes (not cached fixture)
- Redirect to `/session/:session_id` occurs after completion
- Session detail page displays complete analysis
- No `?fixture=1` parameter in URL (indicates real pipeline, not fixture)
- No errors in console

**Test Data**: Valid TORCS .json or FastF1 .parquet file (≤25 MB)

**Priority**: High

**Note**: Unlike demo fixtures which load instantly from cache, uploading your own file runs the full backend pipeline including zone detection, reasoning, and safety review. If no custom file available, mark as SKIP.

---

### TC-009: Invalid File Upload
**Objective**: Verify error handling for invalid files

**Steps**:
1. Navigate to `/upload`
2. Locate "BRING YOUR OWN" dropzone
3. Attempt to upload invalid file (e.g., .txt, .pdf, oversized file >25 MB, or corrupted .json/.parquet)
4. Observe error message below dropzone

**Expected Results**:
- Error message appears in red alert box below dropzone
- Error message is clear and explains what went wrong
- Dropzone remains interactive (user can try again)
- Application remains stable
- No console errors beyond expected validation failures

**Test Data**: Invalid file (non-.json/.parquet, >25 MB, or corrupted file)

**Priority**: Medium

---

### TC-010: Live Capture Ingestion (TORCS)
**Objective**: Verify TORCS telemetry captures can be ingested from shared volume

**Steps**:
1. Ensure TORCS service is running and has generated telemetry captures
2. Navigate to `/upload`
3. Locate "LIVE CAPTURE" section in right pane
4. Below "Race Control" card, locate "Captures on disk" section
5. Observe the run count (e.g., "4 runs")
6. Observe list of individual capture entries showing:
   - Run ID (filename without .jsonl extension)
   - File size in KB
   - Estimated lap count
   - "INGESTED" badge if already processed
7. For a capture not yet ingested, click "Ingest →" button
8. Observe loading state during ingestion
9. Wait for ingestion to complete (~30 seconds)
10. Verify redirect to session detail page

**Expected Results**:
- "Captures on disk" section displays with run count
- Each run entry shows: run ID (truncated with ellipsis if long), size in KB, lap count estimate
- "Ingest →" button appears for new captures (orange accent background)
- "Open →" link appears for already-ingested captures (with "INGESTED" badge)
- Delete button (×) appears for each run
- Ingestion triggers real backend pipeline
- Redirect to `/session/:session_id` occurs after completion
- Session detail page displays complete analysis
- No errors in console

**Test Data**: TORCS telemetry captures in shared volume (JSONL files)

**Priority**: High

**Note**: This feature requires TORCS service running with shared volume mounted. If TORCS not available, mark as SKIP.

**Priority**: High

**Note**: Requires TORCS service running. If not available, mark as SKIP

---

### TC-011: Capture Deletion
**Objective**: Verify capture files can be deleted

**Steps**:
1. Navigate to `/upload` with TORCS running
2. Locate a capture file in live captures list
3. Click delete icon/button
4. Confirm deletion in dialog
5. Verify capture is removed from list

**Expected Results**:
- Delete button is clearly visible
- Confirmation dialog appears
- After confirmation, capture is removed
- List updates immediately
- No errors occur

**Test Data**: TORCS capture file

**Priority**: Medium

**Note**: Requires TORCS service. If not available, mark as SKIP

---

## Phase 3: Session Analysis (Post-Race)

### TC-012: Session Detail Page Load (Completed Session)
**Objective**: Verify session detail page displays all components for completed sessions

**Steps**:
1. Complete one of the following to create/access a session:
   - **Option A**: Click a demo fixture card from `/upload` (e.g., "TORCS engineer demo")
   - **Option B**: Upload a file from `/upload` and wait for pipeline completion
   - **Option C**: Navigate to `/sessions` and click an existing completed session row
2. Verify automatic redirect to `/session/:session_id` (or direct navigation if Option C)
3. Observe all page sections from top to bottom

**Expected Results**:

**Header Section**:
- Session title: "OVERRIDE"
- Session metadata: Track name · lap count · upload timestamp
- Mode toggle: Engineer/Fan buttons (Engineer selected by default)
- Driver profile chips (if TORCS session): Profile name + origin badge

**KPI Strip** (above the fold):
- HARVEST: Total energy harvested (MJ)
- DEPLOY: Total energy deployed (MJ)
- LAPS: Total lap count
- ZONES: Number of detected zones (with severity breakdown if >0)
- SAFETY FLOOR: Minimum SoC value (0.00-1.00 scale)
- FINAL SOC: Ending battery state (percentage)
- CITATION: Regulation section reference (e.g., "§ SECTION...")
- VALIDATOR: Pass status (2/2 or failure indicators)

**Post-Race Report Panel**:
- Executive summary with 4 scored dimensions:
  - DRIVER (0-100)
  - BATTERY (0-100)
  - CONSISTENCY (0-100)
  - RISK (0-100)
- AI commentary section with key moments and insights

**Energy Curve Chart**:
- X-axis: Lap numbers
- Y-axis: State of Charge (0-100%)
- Line plot showing SoC progression
- Triangle markers for zone locations (clickable)
- Forecast line (if available, dashed)
- Hover tooltips showing lap details

**Zone Heatmap**:
- Grid layout: Laps (columns) × Zones (rows)
- Color-coded cells by severity (late-recharge-full, low-roi-deploy, etc.)
- Clickable cells scroll to corresponding recommendation card
- Empty state if no zones detected

**Recommendations Section**:
- Section header: "Recommendations (N)"
- If zones detected:
  - One card per zone with:
    - Zone ID and severity badge
    - Lap range and affected laps
    - Technical explanation (Engineer mode) or simplified text (Fan mode)
    - What-If rail (Engineer mode only) with perturbation options
    - Grounding citations
- If no zones: "No inefficient zones detected" empty state

**Footer**:
- Regulation source citation: "Grounded in [document_title], [issue] · § [section]"
- Link to FIA source document (opens in new tab)

**General**:
- All sections render without errors
- No console errors
- Page is responsive and scrollable
- Zone clicks (from curve/heatmap) scroll to matching recommendation card

**Test Data**: Completed session with zones (e.g., TORCS engineer demo fixture)

**Priority**: Critical

**Note**: For active/live sessions, see TC-023 (Live Race Session). Active sessions show different UI with live telemetry panel and suppressed analysis sections until ingestion.

---

### TC-013: Engineer vs Fan Mode Toggle
**Objective**: Verify mode switching works correctly

**Steps**:
1. On session detail page, locate mode toggle (Engineer/Fan)
2. Verify "Engineer" is selected by default
3. Click "Fan" mode
4. Observe recommendation cards update
5. Click "Engineer" mode
6. Observe cards revert to technical language

**Expected Results**:
- Toggle is clearly visible
- Engineer mode shows technical terminology
- Fan mode shows plain-language explanations
- Mode switch is instant (or shows loading for lazy-loaded fan content)
- Failed fan-mode zones fall back to Engineer with warning

**Test Data**: Session with recommendations

**Priority**: High

---

### TC-014: Recommendation Card Interaction
**Objective**: Verify recommendation cards display all information

**Steps**:
1. On session detail page, locate a recommendation card
2. Observe card structure
3. Click to expand reasoning chain (if collapsed)
4. Observe citation in right rail
5. Check validator and Guardian badges in footer

**Expected Results**:
- **Headline**: Shows recommendation text
- **Metadata**: Displays lap, sector, zone type, severity
- **Cause/Consequence**: Clearly explained
- **Reasoning chain**: Expandable/collapsible
- **Citation**: FIA regulation reference visible
- **Badges**: Validator pass/fail, Guardian score, confidence level
- All text is readable and properly formatted

**Test Data**: Session with recommendations

**Priority**: Critical

---

### TC-015: Zone Deep Link
**Objective**: Verify direct zone linking works

**Steps**:
1. From session detail page, copy URL
2. Append `?zone=<zone_id>` to URL (use actual zone ID from page)
3. Navigate to modified URL
4. Observe page scrolls to specific zone card

**Expected Results**:
- Page loads normally
- Automatically scrolls to specified zone
- Zone card is highlighted or focused
- URL parameter is preserved

**Test Data**: Session with multiple zones

**Priority**: Medium

---

### TC-016: Energy Curve Interaction
**Objective**: Verify energy curve chart is interactive

**Steps**:
1. On session detail page, locate energy curve chart
2. Hover over data points
3. Observe tooltips
4. Check if chart is responsive to window resize

**Expected Results**:
- Chart renders correctly
- Hover shows lap number and SoC value
- Chart adapts to window size
- Data is accurate and matches session data

**Test Data**: Session with lap data

**Priority**: High

---

### TC-017: Zone Heatmap Interaction
**Objective**: Verify zone heatmap displays patterns

**Steps**:
1. On session detail page, locate zone heatmap
2. Observe color coding by severity
3. Hover over cells (if interactive)
4. Verify legend is clear

**Expected Results**:
- Heatmap renders with correct dimensions
- Colors represent severity levels clearly
- Legend explains color coding
- Heatmap is readable and informative

**Test Data**: Session with multiple zones

**Priority**: Medium

---

### TC-018: Post-Race Report Export
**Objective**: Verify report can be exported to PDF

**Steps**:
1. On session detail page, locate "Export Report" or print button
2. Click export action
3. Use browser's print/save-to-PDF function
4. Verify PDF contains all report content

**Expected Results**:
- Export action triggers browser print dialog
- PDF preview shows formatted report
- All sections are included and readable
- Charts and tables render correctly in PDF

**Test Data**: Completed session

**Priority**: Medium

---

### TC-019: Lap Detail Drill-Down
**Objective**: Verify lap-specific analysis page

**Steps**:
1. From session detail page, click on a lap number or lap link
2. Navigate to `/session/:session_id/laps/:lap_number`
3. Observe lap detail page

**Expected Results**:
- **Back link**: Returns to session detail
- **Lap headline**: Shows lap number and summary
- **Lap metrics strip**: Displays lap-specific stats
- **Sector callouts**: Shows sector times
- **Evidence list**: Lists supporting data points
- **Matching recommendations**: Shows zones for this lap
- All data is accurate for selected lap

**Test Data**: Session with multiple laps

**Priority**: High

---

### TC-020: What-If Perturbation
**Objective**: Verify what-if analysis works correctly

**Steps**:
1. On session detail page (Engineer mode), locate a recommendation card
2. Click "What-If" or perturbation button
3. Select a perturbation option (e.g., "Increase harvest by 10%")
4. Wait for analysis to complete
5. Observe before/after diff display

**Expected Results**:
- What-if rail opens with perturbation options
- Selection triggers API call
- Loading indicator appears
- Diff view shows:
  - Before and after mini-cards
  - Metric deltas
  - Pass/fail badges for both scenarios
  - Perturbation label
- User can dismiss diff and return to base card

**Test Data**: Session with recommendations

**Priority**: High

---

## Phase 4: AI Race Engineer Widget

### TC-021: Widget Launch
**Objective**: Verify AI race engineer widget can be opened

**Steps**:
1. From any session-related page, locate widget launcher (usually bottom-right)
2. Click launcher button
3. Observe widget drawer opens

**Expected Results**:
- Launcher button is visible and accessible
- Widget drawer slides in from side
- Widget displays chat interface
- No errors occur

**Test Data**: Any session

**Priority**: High

---

### TC-022: Ask Question (Grounded)
**Objective**: Verify widget can answer session-specific questions

**Steps**:
1. Open AI race engineer widget
2. Type a question about the current session (e.g., "Why did SoC drop on lap 15?")
3. Press Enter or click Send
4. Observe streaming response

**Expected Results**:
- Question appears in chat as user message
- Loading indicator shows while processing
- Response streams in character-by-character
- Response includes:
  - Grounded answer based on session data
  - Supporting lap links (clickable)
  - Follow-up suggestion chips
- Response is relevant and accurate

**Test Data**: Completed session with zones

**Priority**: Critical

---

### TC-023: Widget Persistence
**Objective**: Verify widget maintains state across navigation

**Steps**:
1. Open widget on session detail page
2. Ask a question and receive response
3. Navigate to lap detail page (same session)
4. Open widget again
5. Verify previous conversation is still visible

**Expected Results**:
- Widget remembers conversation history
- Previous messages are displayed
- Context is maintained within same session
- Widget state persists in sessionStorage

**Test Data**: Session with multiple laps

**Priority**: Medium

---

### TC-024: Widget Unread Badge
**Objective**: Verify unread indicator works

**Steps**:
1. Open widget and ask a question
2. Close widget before response completes
3. Wait for response to arrive
4. Observe launcher button

**Expected Results**:
- Unread badge appears on launcher
- Badge shows number of unread messages
- Opening widget clears badge
- Badge is visually distinct

**Test Data**: Any session

**Priority**: Low

---

### TC-025: Widget on Cockpit Page
**Objective**: Verify widget works during live race

**Steps**:
1. Start a live TORCS race
2. Navigate to `/cockpit`
3. Open AI race engineer widget
4. Ask a question about current race state
5. Observe response

**Expected Results**:
- Widget opens correctly on cockpit page
- Context badge shows "Live Race"
- Widget uses same SSE stream as cockpit (no duplicate connections)
- Responses are relevant to live race state
- Widget does not interfere with cockpit functionality

**Test Data**: Active TORCS race

**Priority**: High

**Note**: Requires TORCS service and active race. If not available, mark as SKIP

---

## Phase 5: Session Management

### TC-026: Sessions List Page
**Objective**: Verify sessions list displays and functions correctly

**Steps**:
1. Navigate to `/sessions`
2. Observe page header showing "Sessions" title
3. Observe "Compare" button in top-right (disabled when <2 sessions selected)
4. Observe session list table with all columns
5. Verify each session row displays complete information
6. Test checkbox selection for comparison feature
7. Test delete functionality (× button)

**Expected Results**:
- Sessions display in newest-first order (most recent at top)
- Each row shows:
  - **Checkbox** (left edge) for comparison selection
  - **Session ID/name** (truncated with ellipsis if long)
  - **Source badge**: "torcs" (with "LIVE" badge if from live capture) or "fastf1"
  - **Track name**: Track identifier (e.g., "G-track-1") or "—" if not applicable
  - **Lap count**: Number of laps (e.g., "75 laps")
  - **Zone count**: Number of detected zones (e.g., "49 zones" or "0 zones")
  - **Duration**: Session duration (e.g., "148m 39s", "82m 17s", or "9m 55s")
  - **Timestamp**: Creation date/time (e.g., "May 22, 2026, 08:01 PM")
  - **Delete button** (× on right edge)
- Clicking session row navigates to session detail page
- Checkboxes allow multi-select for comparison
- "Compare" button enables only when exactly 2 sessions selected
- Delete button (×) removes session after confirmation
- Empty state displays if no sessions (with link to upload page)
- No pagination visible (all sessions shown in single scrollable list)

**Test Data**: Multiple sessions (mix of TORCS live, TORCS fixture, and FastF1)

**Priority**: High

---

### TC-027: Session Selection and Comparison
**Objective**: Verify session comparison feature

**Steps**:
1. Navigate to `/sessions`
2. Select exactly two sessions using checkboxes
3. Click "Compare" button
4. Verify redirect to `/sessions/compare?a=<id1>&b=<id2>`
5. Observe comparison view

**Expected Results**:
- Checkboxes allow multi-select
- Compare button enables only when exactly 2 selected
- Comparison page shows side-by-side:
  - Session metadata
  - Pipeline stats
  - KPI comparison
  - Links to drill into each session
- Comparison is clear and informative

**Test Data**: At least 2 sessions

**Priority**: Medium

---

### TC-028: Single Session Deletion
**Objective**: Verify individual session can be deleted

**Steps**:
1. Navigate to `/sessions`
2. Locate delete button on a session row
3. Click delete
4. Confirm deletion in dialog
5. Verify session is removed from list

**Expected Results**:
- Delete button is clearly visible
- Confirmation dialog appears with session details
- Option to delete source telemetry (if TORCS session)
- After confirmation, session is removed
- List updates immediately
- Success message appears

**Test Data**: At least 1 session

**Priority**: High

---

### TC-029: Bulk Session Deletion
**Objective**: Verify multiple sessions can be deleted at once

**Steps**:
1. Navigate to `/sessions`
2. Select multiple sessions using checkboxes
3. Click "Bulk Delete" button
4. Confirm deletion in dialog
5. Verify all selected sessions are removed

**Expected Results**:
- Bulk delete button enables when ≥1 session selected
- Confirmation dialog lists all sessions to be deleted
- Option to delete source telemetry for TORCS sessions
- After confirmation, all sessions are removed
- List updates correctly
- Success message shows count deleted

**Test Data**: Multiple sessions

**Priority**: Medium

---

## Phase 6: TORCS Live Race Features

### TC-030: Driver Lab Page
**Objective**: Verify driver profile management works

**Steps**:
1. Navigate to `/driver-lab`
2. Observe profile list
3. Load a shipped profile
4. Edit profile parameters
5. Validate configuration
6. Save as new profile

**Expected Results**:
- Profile list displays shipped and user profiles
- Profile loads into editor correctly
- All parameters are editable
- Validation provides feedback
- Save creates new profile
- New profile appears in list

**Test Data**: None (uses shipped profiles)

**Priority**: Medium

**Note**: Requires TORCS service. If not available, mark as SKIP

---

### TC-031: Profile Duplication
**Objective**: Verify profile can be duplicated

**Steps**:
1. On Driver Lab page, select a profile
2. Click "Duplicate" button
3. Observe new profile created
4. Verify new profile has same parameters

**Expected Results**:
- Duplicate action creates new profile
- New profile has unique ID
- Parameters match original
- New profile is editable

**Test Data**: Any driver profile

**Priority**: Low

**Note**: Requires TORCS service. If not available, mark as SKIP

---

### TC-032: Profile Deletion
**Objective**: Verify user-created profiles can be deleted

**Steps**:
1. On Driver Lab page, create or select a user profile
2. Click delete button
3. Confirm deletion
4. Verify profile is removed

**Expected Results**:
- Delete button only appears for user profiles (not shipped)
- Confirmation dialog appears
- Profile is removed from list
- Shipped profiles cannot be deleted

**Test Data**: User-created profile

**Priority**: Low

**Note**: Requires TORCS service. If not available, mark as SKIP

---

### TC-033: Start Live Race from Upload Page
**Objective**: Verify race can be configured and started from Race Control

**Steps**:
1. Navigate to `/upload`
2. Locate "LIVE CAPTURE" section in right pane
3. Locate "Race Control" card with "Live" status indicator
4. Configure race parameters:
   - **TRACK**: Select track from dropdown (e.g., "Aalborg")
   - **LAPS**: Set lap count (e.g., "75")
   - **LAUNCH MODE**: Select "Visible Practice" (3D TORCS race display) or "Headless Capture" (Fast race without 3D)
   - **DRIVER PROFILE**: Select driver from dropdown (e.g., "Baseline Demo Driver")
5. Observe driver profile description and "Driver Lab ↗" link
6. Observe "OVERRIDE owns the supported visible Practice path here" note
7. Click "Start race" button (orange accent button)
8. Verify automatic redirect to `/cockpit`
9. Observe cockpit loads with live telemetry

**Expected Results**:
- Track dropdown shows available tracks with preview image
- Laps input accepts numeric values
- Launch mode toggle works (Visible Practice selected by default with orange accent)
- Driver profile dropdown shows available profiles
- "Driver Lab ↗" link opens driver management page
- "Start race" button is enabled when all fields configured
- Clicking "Start race" triggers race launch
- Automatic redirect to `/cockpit` occurs
- Cockpit displays:
  - "COCKPIT" badge with "Live" indicator
  - SESSION ID with session name
  - "CLOSED LAP 0 closed / [total]" counter
  - TRACK name
  - PROFILE name
  - MODE indicator (Visible Practice)
  - "Stop race" and "Configure next run" buttons
  - Live telemetry panels (timing, hybrid energy, lap timeline)
  - noVNC iframe (if Visible Practice) or headless placeholder
- Session stub is created in backend
- No errors in console

**Alternative Access**:
- After starting race, can return to `/upload` and click "Open cockpit view ↗" link to access cockpit

**Test Data**: TORCS service running

**Priority**: Critical

**Note**: Requires TORCS service. If not available, mark as SKIP

---

### TC-034: Cockpit Live Telemetry Display
**Objective**: Verify cockpit displays live race data in real-time

**Steps**:
1. Start a live race (TC-033) - should auto-redirect to `/cockpit`
2. Observe all cockpit sections and panels
3. Watch data update in real-time as race progresses
4. Scroll down to see all sections

**Expected Results**:

**Top Header Bar**:
- "Back" button (returns to `/upload`)
- "COCKPIT" badge with "Live" indicator
- SESSION ID with truncated session name
- "CLOSED LAP X closed / Y" counter (updates per lap)
- TRACK name (e.g., "g-track-1")
- PROFILE name (e.g., "Baseline Demo Driver")
- MODE indicator (e.g., "Visible Practice")
- "Fullscreen" button (top-right)

**Control Buttons**:
- "Stop race" button (stops TORCS race)
- "Configure next run" button (returns to race setup)

**Banner Section**:
- "OVERRIDE LIVE COCKPIT" heading
- "Race live. OVERRIDE is tracking the run in real time." message
- Explanation text about first closed lap upgrade

**Left Rail - TIMING**:
- CURRENT LAP: "X/Y" (e.g., "1/75")
- CURRENT TIME: Live lap time (e.g., "97.71s")
- LIVE SPEED: Current speed in km/h (e.g., "85 km/h")
- LIVE AVG: Average speed in km/h (e.g., "63 km/h")
- FUEL: Current fuel in kg (e.g., "93.8 kg")
- STATE: "live" indicator

**Center Frame**:
- noVNC iframe showing live TORCS 3D race (if Visible Practice mode)
- Live telemetry overlay: "Live telemetry - Sector X, Lap Y, Z% complete"
- Track map overlay with car position indicator
- OR headless placeholder (if Headless Capture mode)

**Right Rail - HYBRID** (with "LIVE" badge):
- SOC: Battery state of charge percentage (e.g., "100%") with "balanced" status
- HARVEST (LAP): Energy harvested current lap in MJ (e.g., "0.12 MJ")
- DEPLOY (LAP): Energy deployed current lap in MJ (e.g., "0.10 MJ")
- NET: Net energy balance in MJ (e.g., "0.01 MJ")
- BALANCE: Energy balance status (e.g., "balanced")
- STATUS: "Telemetry stream live." or lap completion messages

**CLOSED LAP Section** (appears after first lap):
- Lap number and time (e.g., "L1 · 117.628s · 63 km/h avg")
- "REVIEW PENDING" badge

**LAP TIMELINE Section**:
- Header: "LAP TIMELINE" with "X laps received" count
- Individual lap cards showing:
  - Lap number (e.g., "L1")
  - Balance status badge (e.g., "BALANCED")
  - Time (e.g., "117.63s")
  - SoC percentage (e.g., "100%")
  - Harvest energy (e.g., "0.23" in green)
  - Deploy energy (e.g., "0.17" in orange)
  - "REVIEW PENDING" status

**AI RACE ENGINEER Section**:
- Header: "AI RACE ENGINEER"
- Description: "Instant telemetry guardrails stay deterministic. OVERRIDE now auto-requests a Granite readout on closed laps, and you can refresh either live explainer on demand mid-race."
- Mode toggle: Engineer / Fan buttons
- Live commentary card with:
  - "GRANITE LIVE EXPLAINER" or "GRANITE LIVE COMMENTARY" heading
  - "Refresh now" button
  - CONFIDENCE level (e.g., "MEDIUM")
  - Detailed race analysis text
  - Supporting laps reference (e.g., "Supporting laps: 2, 1")
- "INSTANT TELEMETRY GUARDRAIL" section with deterministic insights
- Strategy recommendations

**General Behavior**:
- All data updates smoothly in real-time (no lag or stuttering)
- Lap counter increments as laps complete
- Timing values update continuously
- Hybrid energy values update per lap
- Lap timeline grows as laps complete
- AI commentary auto-refreshes on closed laps
- No console errors
- Page remains responsive during updates

**Test Data**: Active TORCS race with at least 2 completed laps

**Priority**: Critical

**Note**: Requires TORCS service and active race. If not available, mark as SKIP

---

### TC-035: AI Race Engineer During Live Race
**Objective**: Verify AI Race Engineer provides live race insights and answers questions

**Steps**:
1. Start a live race (TC-033) and wait for at least 2 laps to complete
2. Scroll down to "AI RACE ENGINEER" section on cockpit page
3. Observe the widget header and status badges
4. Observe suggested question chips
5. Click a suggested question (e.g., "Are we under battery pressure now?")
6. Observe Granite-backed answer appears
7. Type a custom question in the input field (e.g., "What changed this lap?")
8. Click "Send" button
9. Observe answer streams in
10. Test mode toggle (Engineer/Fan) and observe language changes

**Expected Results**:

**Widget Header**:
- Title: "AI RACE ENGINEER"
- Context: "Live race - [Driver Profile Name]" (e.g., "Live race - Baseline Demo Driver")
- Status badges: "LIVE RACE", "LIVE STREAM", "ACTIVE"
- Description: "Grounded in live telemetry, recent closed laps, and deterministic live insights."
- "Close" button (top-right)

**Suggested Questions** (clickable chips):
- "Are we under battery pressure now?"
- "What changed this lap?"
- "Why did OVERRIDE surface that insight?"
- Questions update based on race context

**Answer Display**:
- Confidence badge: "Granite-backed · medium" (or other confidence level)
- Detailed analysis text referencing:
  - Current battery state (SOC percentage)
  - Energy trends (+/- MJ values)
  - Lap-specific data
  - Strategy recommendations
- Supporting lap references as clickable chips (e.g., "Lap 3", "Lap 1", "Lap 2")
- Answers are contextually relevant to current race state

**Input Field**:
- Text input at bottom of widget
- "Send" button (orange accent)
- Placeholder text guides user input
- Input accepts custom questions

**Mode Toggle**:
- Engineer / Fan buttons
- Engineer mode: Technical language with specific metrics
- Fan mode: Plain-language explanations
- Mode persists across questions

**Footer Note**:
- "Live answers stay grounded in the current stream and recent closed laps."

**General Behavior**:
- Answers reference actual telemetry data (SOC, energy values, lap times)
- Answers cite specific laps that are completed
- Confidence levels are displayed
- No hallucinated data or generic responses
- Widget remains responsive during race
- No console errors

**Test Data**: Active TORCS race with at least 2 completed laps

**Priority**: Critical

**Note**: This is a live-race-specific feature. The AI Race Engineer widget also appears on completed session pages but with different context (post-race analysis vs live insights). Requires TORCS service and active race. If not available, mark as SKIP.

---

### TC-036: Stop Live Race
**Objective**: Verify race can be stopped gracefully

**Steps**:
1. During live race, click "Stop Race" button
2. Confirm stop action
3. Observe race stops
4. Verify telemetry capture is saved

**Expected Results**:
- Stop button is clearly visible
- Confirmation dialog appears
- Race stops immediately
- Telemetry file is saved to shared volume
- Cockpit shows "race stopped" state
- User is prompted to ingest completed race

**Test Data**: Active TORCS race

**Priority**: High

**Note**: Requires TORCS service and active race. If not available, mark as SKIP

---

### TC-037: Cockpit Fullscreen Mode
**Objective**: Verify fullscreen toggle works

**Steps**:
1. On cockpit page, click fullscreen button
2. Observe display enters fullscreen
3. Press Escape or click exit fullscreen
4. Verify returns to normal view

**Expected Results**:
- Fullscreen button is visible
- Clicking enters browser fullscreen mode
- Cockpit layout adapts to fullscreen
- Escape key exits fullscreen
- Layout returns to normal

**Test Data**: Cockpit page (race not required)

**Priority**: Low

---

### TC-038: Cockpit Recovery Action
**Objective**: Verify recovery action resets simulator

**Steps**:
1. On cockpit page, click "Recover" button
2. Confirm recovery action
3. Observe simulator resets

**Expected Results**:
- Recovery button is accessible
- Confirmation dialog explains action
- Simulator resets to stable state
- Cockpit updates to reflect reset
- No data loss for completed sessions

**Test Data**: TORCS service running

**Priority**: Medium

**Note**: Requires TORCS service. If not available, mark as SKIP

---

## Phase 7: Edge Cases & Error Handling

### TC-039: Grounding Unavailable Banner
**Objective**: Verify banner displays when regulation grounding is unavailable

**Steps**:
1. Create session before Gate G-4 verification (or simulate unavailable state)
2. Navigate to session detail page
3. Observe grounding-pending banner

**Expected Results**:
- Banner displays prominently
- Message explains regulation grounding is unavailable
- Recommendations still display without citations
- User can proceed with analysis

**Test Data**: Session without regulation grounding

**Priority**: Medium

**Note**: May not be testable if G-4 is complete. Mark as SKIP if not applicable

---

### TC-040: Terminal Validator Failure
**Objective**: Verify validator failure is clearly communicated

**Steps**:
1. Create session with data that triggers validator failure
2. Navigate to session detail page
3. Locate failed recommendation card

**Expected Results**:
- Card displays validator failure state
- Failed rules are listed
- Notes explain what went wrong
- Card is visually distinct from passing cards
- User understands why recommendation failed

**Test Data**: Session with validator failures

**Priority**: High

**Note**: May require specific test data. If not available, mark as SKIP

---

### TC-041: Low Confidence Recommendation
**Objective**: Verify low-confidence recommendations are marked

**Steps**:
1. Create session with low-confidence recommendation
2. Navigate to session detail page
3. Locate low-confidence card

**Expected Results**:
- Card displays low-confidence banner
- Banner explains recommendation is exploratory
- Guardian score is visible
- User understands confidence level
- Recommendation still provides value

**Test Data**: Session with low-confidence zones

**Priority**: Medium

**Note**: May require specific test data. If not available, mark as SKIP

---

### TC-042: Empty Session State
**Objective**: Verify empty state handling

**Steps**:
1. Navigate to `/sessions` with no sessions created
2. Observe empty state

**Expected Results**:
- Clear message explains no sessions exist
- Call-to-action button links to `/upload`
- Empty state is visually appealing
- User knows what to do next

**Test Data**: Fresh installation or deleted all sessions

**Priority**: Low

---

### TC-043: Network Error Handling
**Objective**: Verify graceful handling of network errors

**Steps**:
1. Simulate network error (disconnect network or stop backend)
2. Attempt to create session or load data
3. Observe error message

**Expected Results**:
- Clear error message displays
- Error explains what went wrong
- User can retry action
- Application remains stable
- No console errors cascade

**Test Data**: Network disconnection

**Priority**: Medium

**Note**: Requires manual network manipulation. Test carefully.

---

### TC-044: Browser Compatibility
**Objective**: Verify application works in multiple browsers

**Steps**:
1. Test application in Chrome/Chromium
2. Test application in Firefox
3. Test application in Safari (if available)
4. Test application in Edge

**Expected Results**:
- All features work consistently across browsers
- Layout renders correctly
- No browser-specific errors
- Performance is acceptable

**Test Data**: Any session

**Priority**: Medium

**Note**: Test in available browsers only. Document which browsers tested.

---

### TC-045: Responsive Design
**Objective**: Verify application works on different screen sizes

**Steps**:
1. Test application at desktop resolution (1920x1080)
2. Test at laptop resolution (1366x768)
3. Test at tablet resolution (768x1024)
4. Test at mobile resolution (375x667)

**Expected Results**:
- Layout adapts to screen size
- All content remains accessible
- Navigation works on all sizes
- Charts and tables are readable
- No horizontal scrolling (except tables)

**Test Data**: Any session

**Priority**: High

**Note**: Use browser DevTools responsive mode for testing

---

## Phase 8: Performance & Stability

### TC-046: Pipeline Performance
**Objective**: Verify pipeline completes within acceptable time

**Steps**:
1. Upload sample replay
2. Measure time from upload to session detail page load
3. Record pipeline duration

**Expected Results**:
- Pipeline completes in ≤ 15 seconds
- No timeouts occur
- Progress indicators work correctly
- Session data is complete

**Test Data**: Sample replay

**Priority**: High

---

### TC-047: Page Load Performance
**Objective**: Verify pages load quickly

**Steps**:
1. Navigate to each major page
2. Measure load time using browser DevTools
3. Record performance metrics

**Expected Results**:
- Initial page load ≤ 3 seconds
- Subsequent navigation ≤ 1 second
- No performance warnings in console
- Smooth animations and transitions

**Test Data**: Multiple sessions

**Priority**: Medium

---

### TC-048: Memory Leak Check
**Objective**: Verify no memory leaks during extended use

**Steps**:
1. Open browser DevTools Memory profiler
2. Take initial heap snapshot
3. Navigate through multiple pages and sessions
4. Return to starting page
5. Force garbage collection
6. Take final heap snapshot
7. Compare memory usage

**Expected Results**:
- Memory usage returns to baseline after GC
- No significant memory growth
- No detached DOM nodes
- No event listener leaks

**Test Data**: Multiple sessions

**Priority**: Low

**Note**: Requires DevTools proficiency. Optional test.

---

### TC-049: Concurrent User Simulation
**Objective**: Verify application handles multiple users

**Steps**:
1. Open application in multiple browser tabs/windows
2. Perform different actions in each
3. Verify no conflicts or errors

**Expected Results**:
- Each tab operates independently
- No session conflicts
- No data corruption
- All tabs remain functional

**Test Data**: Multiple sessions

**Priority**: Low

---

### TC-050: Long-Running Session
**Objective**: Verify application handles large sessions

**Steps**:
1. Create or load session with many laps (50+)
2. Navigate through session detail page
3. Observe performance

**Expected Results**:
- Page loads successfully
- Charts render all data
- Scrolling is smooth
- No performance degradation
- All features remain functional

**Test Data**: Large session (50+ laps)

**Priority**: Medium

**Note**: May require specific test data. If not available, mark as SKIP

---

## Test Execution Summary Template

### Test Session Information
- **Tester Name**: _______________
- **Date**: _______________
- **Environment**: _______________
- **Browser**: _______________
- **Screen Resolution**: _______________

### Results Summary
- **Total Tests**: 50
- **Passed**: ___
- **Failed**: ___
- **Partial**: ___
- **Skipped**: ___

### Critical Issues Found
1. _______________
2. _______________
3. _______________

### High Priority Issues Found
1. _______________
2. _______________
3. _______________

### Recommendations for Demo
1. _______________
2. _______________
3. _______________

### Sign-Off
- **Tester Signature**: _______________
- **Date**: _______________
- **Ready for Demo**: ☐ Yes  ☐ No  ☐ With Caveats

---

## Appendix A: Test Data Setup

### Creating Test Sessions

**Sample Replay (Fastest)**:
```
1. Navigate to /upload
2. Click "Analyze" on any sample replay
3. Wait for completion
```

**TORCS Live Session**:
```
1. Start TORCS: podman-compose up override torcs
2. Navigate to /cockpit
3. Select track and driver profile
4. Click "Start Race"
5. Let race run for 10-15 laps
6. Click "Stop Race"
7. Navigate to /upload
8. Click "Ingest" on new capture
```

**Custom Upload**:
```
1. Obtain valid JSONL telemetry file
2. Navigate to /upload
3. Upload file
4. Wait for processing
```

---

## Appendix B: Known Limitations

### Current Version Limitations
1. **TTM-R2 Forecasting**: Requires separate Docker service (`podman-compose up override ttm`)
2. **TORCS Features**: Require TORCS service running
3. **Regulation Grounding**: Requires Gate G-4 verification complete
4. **CI Workflows**: Deferred to v1.1
5. **Guardian Model**: May be deprecated by IBM in future

### Expected Behaviors
1. **TTM Unavailable**: Pipeline gracefully degrades, returns `None` for forecast
2. **Short Sessions**: Sessions <30 laps skip TTM forecasting
3. **Fan Mode Failures**: Fall back to Engineer mode with warning
4. **TORCS Unavailable**: Live features hidden, fixture mode available

---

## Appendix C: Demo Recording Checklist

### Pre-Recording Setup
- [ ] Application running and tested
- [ ] Sample data prepared
- [ ] Browser window sized appropriately
- [ ] Screen recording software configured
- [ ] Audio levels tested
- [ ] Script/talking points prepared

### Demo Flow Recommendation
1. **Introduction** (0:00-0:15)
   - Show landing page
   - Explain OVERRIDE purpose

2. **Quick Analysis** (0:15-0:45)
   - Upload sample replay
   - Show pipeline processing
   - Navigate to session detail

3. **Explainability** (0:45-1:30)
   - Show recommendation cards
   - Toggle Engineer/Fan modes
   - Highlight FIA grounding
   - Show reasoning chain

4. **AI Race Engineer** (1:30-2:00)
   - Open widget
   - Ask question
   - Show grounded response

5. **What-If Analysis** (2:00-2:20)
   - Select recommendation
   - Run perturbation
   - Show before/after diff

6. **Live Race** (2:20-2:45) [Optional]
   - Show cockpit
   - Start race
   - Show live telemetry
   - Stop and ingest

7. **Closing** (2:45-2:55)
   - Recap key features
   - Show IBM technologies
   - Call to action

### Target Runtime
- **Total**: ≤ 2:55
- **Buffer**: 5 seconds for transitions

---

**End of Manual Test Plan**

For questions or issues during testing, refer to:
- [`docs/04-ui-ux-design.md`](04-ui-ux-design.md) - UI/UX details
- [`docs/04-api.md`](04-api.md) - API endpoints
- [`docs/06-testing.md`](06-testing.md) - Automated test coverage
- [`README.md`](../README.md) - Quick start guide