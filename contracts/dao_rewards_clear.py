from pyteal import *

def rewards_clear_state_program():
    return Return(Int(1))

with open('rewards_contract_clear.teal', 'w') as f:
    compiled = compileTeal(rewards_clear_state_program(), Mode.Application, version=6)
    f.write(compiled)