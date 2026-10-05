import sys, os
sys.path.insert(0, os.path.abspath("."))
from isaac_sim_hospital.environments.command_interface import parse_natural_command, CommandType

test_commands = [
    "Go to reception.",
    "Deliver medicine to P003.",
    "Deliver the prescribed medicine to P003.",
    "Patient P003 is an emergency.",
    "Who is treating P003?",
    "What medicine is prescribed for P003?",
    "Check patient P003.",
    "Reception-ilottu po.",
    "Emergency aanu, ICU-ilottu vegam po.",
    "P003-nu medicine kondu poyi kodukku."
]

for cmd_text in test_commands:
    cmd = parse_natural_command(cmd_text)
    print(f'Text: "{cmd_text}"')
    print(f'  -> Type: {cmd.cmd_type.name:<14} | Dest: {cmd.destination_location:<8} | Item: {cmd.item:<25} | Arg: {cmd.argument}')
