# Alert System - Tree UI Redesign

## Summary

Redesigned all alert screens to match the Groups UI tree structure style.

**Changes**:
- ✅ Removed all divider lines (━━━━━)
- ✅ Added tree structure (├ └) to all lists
- ✅ Compact formatting throughout
- ✅ Consistent with Groups UI design
- ✅ Mode icons shown inline
- ✅ Preview alerts displayed cleanly

---

## New UI Screens

### **1. Alerts Dashboard**

```
🚨 Alert System

STATUS
🟢 16/16 targets active (100%)

USAGE
📈 PNL          14 targets
🎚️ Threshold    16 targets
⚡ Sensitivity  16 targets
🔄 Dynamic      15 targets
```

**Changes**:
- Removed dividers
- Compact status line
- Clean aligned numbers
- No redundant "alerts" text

---

### **2. Targets Overview**

```
🎯 Targets (16)

🟢 (CH) WEB TRACK
  └ Modes: 4/4 active (📈 🎚️ ⚡ 🔄)

🟢 CURATED ALPHA
  └ Modes: 2/4 active (📈 🎚️)

🟢 Act V
  └ Modes: 4/4 active (📈 🎚️ ⚡ 🔄)

🔴 Disabled Target
  └ Alerts OFF
```

**Changes**:
- Tree structure like Groups
- Shows mode count with icons
- Status emoji first
- Clean hierarchy

---

### **3. Target List (with Preview)**

```
🎯 Targets (Page 1/3)

🟢 (CH) WEB TRACK
  ├ Modes: 4/4 active (📈 🎚️ ⚡ 🔄)
  └ Next: 1.5x, 2.0x, 3.0x, 7.0x

🟢 CURATED ALPHA
  ├ Modes: 2/4 active (📈 🎚️)
  └ Next: 2.0x, 5.0x, 10.0x

🟢 CALL TREND 2.0
  ├ Modes: 3/4 active (🎚️ ⚡ 🔄)
  └ Next: 1.25x, 1.56x, 2.0x, 5.0x
```

**Changes**:
- Two-level tree structure
- Active mode icons shown
- Preview of next 4 alerts
- Compact, scannable format

---

### **4. Target Config Screen**

```
⚙️ CALL TREND 2.0

STATUS
🟢 Alerts ENABLED

MODES
📈 PNL Commands
  └ ❌ Disabled

🎚️ Threshold
  ├ ✅ Active
  └ Values: 2.0x, 5.0x, 10.0x, 25.0x

⚡ Sensitivity
  ├ ✅ Active
  └ Rate: 25% (+0.25 per alert)

🔄 Dynamic Tracking
  └ ✅ Active

PREVIEW
Next alerts: 1.25x, 1.56x, 1.95x, 2.0x, 5.0x, 10.0x...
```

**Changes**:
- Tree structure for each mode
- Status and details indented
- Clean hierarchy (matches Groups exactly)
- No dividers
- All 4 modes visible

---

## Comparison with Groups UI

### **Groups Screen** (Reference)
```
👥 Groups Management (Page 1/4)

✅ swingz
  ├ Quota: ∞/day
  ├ Targets: 1 | Schedules: 0
  └ 🤖 Ash

✅ CALL TREND 2.0
  ├ Quota: ∞/day
  ├ Targets: 1 | Schedules: 0
  └ 🤖 Noir.exe
```

### **Alerts Screen** (Now Matching)
```
🎯 Targets (Page 1/3)

🟢 swingz
  ├ Modes: 4/4 active (📈 🎚️ ⚡ 🔄)
  └ Next: 1.5x, 2.0x, 7.0x, 25.0x

🟢 CALL TREND 2.0
  ├ Modes: 3/4 active (🎚️ ⚡ 🔄)
  └ Next: 1.25x, 2.0x, 5.0x
```

**Perfect Match**:
- ✅ Same tree characters (├ └)
- ✅ Same indentation (2 spaces)
- ✅ Same structure (status → details)
- ✅ Same visual hierarchy
- ✅ Same clean formatting

---

## Files Modified

1. **app/ui/handlers/alerts.py**
   - Removed dividers from dashboard
   - Compact status and usage sections
   - Clean number alignment

2. **app/ui/handlers/targets.py**
   - `show_targets_menu()` - tree structure for overview
   - `show_targets_for_alerts()` - tree structure with preview
   - `show_alerts_menu()` - tree structure for mode config
   - Mode icons displayed inline
   - Next alerts preview added

---

## Key Improvements

| Aspect | Before | After |
|--------|--------|-------|
| Visual noise | High (many dividers) | Low (clean) |
| Structure | Inconsistent | Tree-based |
| Mode visibility | Limited | Icons shown |
| Preview | Separate section | Inline with target |
| Style match | Different from Groups | Identical to Groups |

---

## Example Flow

**User Journey**:
1. Tap "Alerts" → See clean dashboard
2. Tap "Configure Targets" → See tree list with previews
3. Tap target → See tree-structured mode config
4. All screens consistent, no dividers, clean hierarchy

**Visual Consistency**:
- Groups, Alerts, Targets all use same tree UI
- User learns pattern once, applies everywhere
- Professional, modern appearance

---

**Status**: ✅ COMPLETE - Tree UI implemented across all alert screens
