# Case Study: Multi-Agent Blood Supply and Cold-Chain Management

## 1. Project Background and Clinical Motivation

Emergency blood banking and hospital distribution involve strict medical constraints:
- Blood products (e.g., packed red blood cells) are perishable, with clinical shelf-life limits.
- Cold-chain regulations mandate maintaining temperatures between 1.0°C and 10.0°C during transit to prevent spoilage and transfusion complications.
- Blood groups follow strict immunological compatibility rules (ABO and Rh factors).
- Supply is limited, requiring fair and clinical-priority-driven allocation during mass emergencies without permanently starving routine elective surgeries.

This project implements a multi-agent system where hospital demand, regional blood banking, logistics pathfinding, and thermal safety monitoring are modeled as interacting software agents.

---

## 2. PEAS Analysis (Performance, Environment, Actuators, Sensors)

### Hospital Agent (`H1` to `H5`)
- **Performance Measure:** Fulfillment rate of surgical requirements, waiting time until delivery, zero accepted shipments with unverified or breached cold-chain records.
- **Environment:** Clinical operating theater schedule, hospital on-site blood storage, regional MessageBus.
- **Actuators:** Message emitter (`REQUEST` for blood units, `ACK` acknowledging receipt).
- **Sensors:** Local blood inventory level, incoming surgical queue, delivery vehicle arrival events and delivery temperature records.

### Central Blood Bank Agent (`CBB`)
- **Performance Measure:** Clinical priority alignment (maximizing fulfillment of high-urgency and imminent-need surgeries), shelf-life preservation via FEFO, minimization of stockouts and waste, fair service without indefinite starvation of routine requests.
- **Environment:** Regional hospital network, primary blood inventory, delivery vehicle fleet, peer Reserve Blood Bank.
- **Actuators:** Allocation engine, vehicle dispatch orders (`DISPATCH`), negotiation performatives (`INFORM`, `REFUSE`, `BACKUP_REQUEST`).
- **Sensors:** Message inbox (hospital requirements, vehicle telemetry, peer bank responses), inventory expiration records.

### Reserve Blood Bank Agent (`RBB`)
- **Performance Measure:** Rapid emergency responsiveness, accurate contingency stock preservation, successful fulfillment of backup requests.
- **Environment:** Strategic buffer inventory, secondary vehicle fleet, regional MessageBus.
- **Actuators:** Secondary vehicle dispatch orders (`DISPATCH`), negotiation responses (`PROPOSE`, `REFUSE`).
- **Sensors:** Message inbox (`BACKUP_REQUEST` from Central Blood Bank), reserve inventory monitor.

### Delivery Agent (`VAN-01` to `VAN-04`)
- **Performance Measure:** On-time arrival within surgical deadline, route travel-time minimization, zero undetected cold-chain breaches.
- **Environment:** Urban road network topology with distance and traffic delay factors, ambient thermal conditions.
- **Actuators:** Vehicle position stepper, route navigator, MessageBus emitter (`STATUS_UPDATE`, `ACCEPT`, `BREACH_ALERT`, `DELIVERED`).
- **Sensors:** GPS coordinate tracker, edge traversal progress, simulated onboard thermocouple sensor.

---

## 3. Environment Characterization

Following Russell & Norvig's classification of task environments:

| Dimension | Classification | Description in this System |
| :--- | :--- | :--- |
| **Observability** | **Partially Observable** | Individual hospitals observe only their local inventory and surgical schedule. The blood bank perceives hospital needs only when explicit `REQUEST` messages are received. Delivery agents perceive only their assigned route, current edge, and onboard temperature. |
| **Agent Multiplicity** | **Multi-Agent (Cooperative)** | Multiple autonomous agents (hospitals, blood banks, couriers) communicate to optimize patient outcomes and cold-chain compliance. |
| **Determinism** | **Deterministic (Config-seeded)** | The simulation executes deterministically when initialized with a fixed random seed. Stochastic temperature drift is seed-controlled for repeatable test verification. |
| **Episodic vs. Sequential** | **Sequential** | Current allocation decisions deplete inventory and occupy vehicles, directly impacting future capacity to serve subsequent surgical emergencies. |
| **Static vs. Dynamic** | **Dynamic** | The simulation clock advances time. Cargo temperatures change, shelf lives elapse, and traffic delays affect transit times while decisions are being executed. |
| **Discrete vs. Continuous** | **Discrete-Time** | The simulation proceeds in synchronous discrete-time ticks ($\Delta t = 1.0$ minute) over a continuous/discrete road graph. |
| **Known vs. Unknown** | **Known** | The road network topology, node coordinates, compatibility rules, and safety bounds are fully defined in configuration. |
