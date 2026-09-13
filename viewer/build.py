"""
Data for the trace viewer, from real runs of experiment 1.

    python3 viewer/build.py      then open viewer/index.html

Every trace is the gate's actual journal for that fault and tier, not a mock-up.
Re-run this after changing the gate.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "experiments"))
import refund_agent

data = {
    "faults": refund_agent.FAULTS,
    "results": {fault: {name: refund_agent.run(system, tier, fault, keep_journal=True)
                        for system, tier, name in refund_agent.SYSTEMS}
                for fault in refund_agent.FAULTS},
}
with open(os.path.join(HERE, "traces.js"), "w") as f:
    f.write("window.INTERLOCK_TRACES = " + json.dumps(data, indent=1) + ";\n")
print(f"wrote viewer/traces.js: {len(data['faults'])} faults, 5 systems each")
