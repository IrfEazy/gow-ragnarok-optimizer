# Bug Fix: HTTP 500 Error When Selecting Multiple Optimization Stats

## Problem
When users selected more than one optimization stat (e.g., "Strength" and "Defense"), the application returned an HTTP 500 error with the message: "Error saving preferences: HTTP 500" in the bottom right corner, and nothing changed.

## Root Cause
In `_build_step_plan()` function (line 467 in `gow_optimizer/web.py`), the code attempted to access the first element of the Pareto frontier options for each armor/weapon slot:

```python
cur_stats = {slot: options[0][1] for slot, options in slot_pareto.items()}
```

When filtering by multiple target stats, some slots might have an **empty Pareto frontier** (no items satisfy all the specified stats), causing an `IndexError: list index out of range`.

**Example**: If a user selected only "Strength" and "Defense", but Draupnir Spear (one of the armor slots) has no items with both Strength and Defense stats, the Pareto frontier for that slot would be empty, and `options[0]` would fail.

## Solution
Filter out slots with empty Pareto frontiers before trying to access them:

```python
remaining_slots = {slot: list(options) for slot, options in slot_pareto.items() if options}
cur_stats = {slot: options[0][1] for slot, options in slot_pareto.items() if options}
```

This ensures we only create entries for slots that have at least one viable option, skipping empty frontiers gracefully.

## Changes Made
**File**: `gow_optimizer/web.py`
- **Lines 466-467**: Added `if options` filter to both dictionaries in `_build_step_plan()`

## Testing

### Unit Tests
✅ All 15 existing tests pass:
```
pytest tests/test_web.py -xvs
15 passed in 5.09s
```

### Integration Tests (Playwright)
✅ **Single Stat Selection**
- Selected only "Defense"
- Preferences saved and persisted across page reload

✅ **Two Stat Selection**  
- Selected "Strength" and "Defense"
- Grand Total changed from 492 to 480 (reflecting the filtered optimization)
- No HTTP 500 error

✅ **Three Stat Selection**
- Selected "Strength", "Defense", and "Cooldown"
- Grand Total recalculated to 480
- Preferences persisted after page reload

✅ **Reset Functionality**
- Clicked "Ripristina Predefiniti" button
- All stats deselected (empty array = "all stats" mode)
- Grand Total reverted to 492 (full optimization)
- Preferences persisted after page reload

## Technical Details

The issue occurred only when:
1. User selected multiple stats
2. At least one armor/weapon slot had no items matching all the selected stats
3. The Pareto frontier computation returned an empty list for that slot
4. `_build_step_plan()` tried to access index 0 of an empty list

The fix gracefully handles this by skipping slots with no viable options, allowing the step-by-step plan to be built only for slots that have upgrade options matching the selected stats.

## Verification
- ✅ Server logs show no errors
- ✅ No HTTP 500 errors in browser console
- ✅ Multi-stat selections save and persist correctly
- ✅ Page reloads maintain preferences
- ✅ Reset button works correctly
- ✅ All unit tests passing
