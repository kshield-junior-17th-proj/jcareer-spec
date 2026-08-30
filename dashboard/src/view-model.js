export const CUSTOMER_LANE_ORDER = Object.freeze(["candidate", "company", "platform"]);

export function observationCustomerSides(observation) {
  const declared = Array.isArray(observation?.customer_sides)
    ? observation.customer_sides
    : [observation?.customer_side];
  return [...new Set(declared.filter((side) => CUSTOMER_LANE_ORDER.includes(side)))];
}

export function buildObservationLanes(snapshot) {
  const observations = Array.isArray(snapshot?.observations) ? snapshot.observations : [];
  return CUSTOMER_LANE_ORDER.map((side) => ({
    side,
    items: observations.filter((item) => observationCustomerSides(item).includes(side))
  }));
}
