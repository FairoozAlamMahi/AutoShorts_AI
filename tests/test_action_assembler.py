import pytest
from pathlib import Path
try:
    from src.editing import (
        ActionAssembler,
        ActionBeat,
        AssemblyMode,
        action_assembler,
    )
except ImportError:
    from shorts_factory.src.editing import (
        ActionAssembler,
        ActionBeat,
        AssemblyMode,
        action_assembler,
    )


def test_determine_assembly_mode():
    assert action_assembler.determine_assembly_mode("Grand Theft Auto VI") == AssemblyMode.MULTI_CUT_MONTAGE
    assert action_assembler.determine_assembly_mode("GTA Online Police Chase") == AssemblyMode.MULTI_CUT_MONTAGE
    assert action_assembler.determine_assembly_mode("Phantom Blade Zero") == AssemblyMode.SINGLE_CLIMAX_FLOW
    assert action_assembler.determine_assembly_mode("Elden Ring Boss Fight") == AssemblyMode.SINGLE_CLIMAX_FLOW


def test_build_multi_cut_beats():
    beats = action_assembler.build_multi_cut_beats(base_start_sec=100.0)
    assert len(beats) == 4
    assert beats[0].label == "HOOK_SETUP"
    assert beats[1].label == "ESCALATION"
    assert beats[2].label == "PEAK_CLIMAX"
    assert beats[3].label == "RESOLUTION_LOOP"
    total_dur = sum(b.duration_sec for b in beats)
    assert 25.0 <= total_dur <= 32.0
