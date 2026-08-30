import test from "node:test";
import assert from "node:assert/strict";

import { buildObservationLanes, CUSTOMER_LANE_ORDER } from "../src/view-model.js";

test("maps candidate, company and platform observations into stable renderer lanes", () => {
  const observations = [
    { observation_id: "obs-provider", customer_side: "platform" },
    { observation_id: "obs-company-lifecycle", customer_side: "company" },
    { observation_id: "obs-candidate-status", customer_side: "candidate" },
    { observation_id: "obs-company-data", customer_side: "company" }
  ];
  const lanes = buildObservationLanes({ observations });

  assert.deepEqual(lanes.map((lane) => lane.side), [...CUSTOMER_LANE_ORDER]);
  assert.deepEqual(lanes.map((lane) => lane.items.length), [1, 2, 1]);
  assert.deepEqual(
    lanes[1].items.map((item) => item.observation_id),
    ["obs-company-lifecycle", "obs-company-data"]
  );
});

test("returns empty stable lanes when observations are absent", () => {
  const lanes = buildObservationLanes({});
  assert.deepEqual(lanes.map((lane) => lane.items.length), [0, 0, 0]);
});

test("routes one shared observation to both customer lanes without changing the unique record count", () => {
  const observations = [
    {
      observation_id: "obs-shared-status-gate",
      customer_side: "company",
      customer_sides: ["company", "candidate"]
    },
    { observation_id: "obs-platform", customer_side: "platform" }
  ];
  const lanes = buildObservationLanes({ observations });

  assert.equal(observations.length, 2);
  assert.deepEqual(lanes.map((lane) => lane.items.length), [1, 1, 1]);
  assert.equal(lanes[0].items[0], lanes[1].items[0]);
});

test("deduplicates repeated side metadata inside a lane while preserving legacy singular routing", () => {
  const shared = {
    observation_id: "obs-defensive-dedup",
    customer_side: "company",
    customer_sides: ["company", "company"]
  };
  const lanes = buildObservationLanes({ observations: [shared] });
  assert.deepEqual(lanes.map((lane) => lane.items.length), [0, 1, 0]);
});
