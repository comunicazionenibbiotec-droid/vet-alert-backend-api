import express from "express";
import {
  updateSingleEventOutbreakLink,
  recalculateOutbreakWindow,
  rebuildOutbreakSeries,
} from "../services/outbreakJobs.js";

const router = express.Router();

router.post("/outbreaks/rebuild", async (req, res) => {
  try {
    const result = await rebuildOutbreakSeries();

    res.json({
      ok: true,
      job: "outbreaks_rebuild",
      stdout: result.stdout,
      stderr: result.stderr,
    });
  } catch (error) {
    res.status(500).json({
      ok: false,
      job: "outbreaks_rebuild",
      error,
    });
  }
});

router.post("/outbreaks/events/:eventId/update-link", async (req, res) => {
  try {
    const { eventId } = req.params;

    const result = await updateSingleEventOutbreakLink(eventId);

    res.json({
      ok: true,
      job: "single_event_update",
      event_id: eventId,
      stdout: result.stdout,
      stderr: result.stderr,
    });
  } catch (error) {
    res.status(500).json({
      ok: false,
      job: "single_event_update",
      error,
    });
  }
});

router.post("/outbreaks/events/:eventId/recalculate-window", async (req, res) => {
  try {
    const { eventId } = req.params;

    const daysBefore = Number(req.body?.days_before || 30);
    const daysAfter = Number(req.body?.days_after || 30);

    const result = await recalculateOutbreakWindow(eventId, daysBefore, daysAfter);

    res.json({
      ok: true,
      job: "outbreak_window_recalculation",
      event_id: eventId,
      days_before: daysBefore,
      days_after: daysAfter,
      stdout: result.stdout,
      stderr: result.stderr,
    });
  } catch (error) {
    res.status(500).json({
      ok: false,
      job: "outbreak_window_recalculation",
      error,
    });
  }
});

export default router;
