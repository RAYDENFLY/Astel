"""Run 3 agent ticks to generate real data for verification."""
import os
import sys
import time
import logging

os.environ['AGENT_LOOP_INTERVAL_SEC'] = '5'
os.environ['AGENT_LLM_INTERVAL_SEC'] = '30'
os.environ['AGENT_MODE'] = 'execute'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.WARNING)
from agent.agent import AutonomousAgent, _load_agent_config

cfg = _load_agent_config()
cfg['loop_interval_sec'] = 5
cfg['llm_interval_sec'] = 30

agent = AutonomousAgent(cfg)

for i in range(3):
    try:
        agent._tick()
        print(f'Tick {i+1} done at {time.strftime("%H:%M:%S")}')
        time.sleep(2)
    except Exception as e:
        print(f'Tick {i+1} error: {e}')
        break

print('Agent run complete')