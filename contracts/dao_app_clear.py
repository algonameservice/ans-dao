from pyteal import *

def clear_state_program():
    return Return(Int(1))

with open('dao_app_clear_state.teal', 'w') as f:
    compiled = compileTeal(clear_state_program(), Mode.Application, version = 6)
    f.write(compiled)