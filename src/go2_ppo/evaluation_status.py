"""Separate process completion, numeric policy quality and actual recording evidence."""


def substep_events(rows):
    def flag(value):
        if value is True or value == 'True':
            return True
        if value is False or value == 'False':
            return False
        raise ValueError('Invalid physical safety flag')
    physical = boundary = unsafe = False
    first = None
    for row in rows:
        p = flag(row['physical_fallen'])
        b = flag(row['out_of_terrain'])
        event = p or b or flag(row['fallen'])
        physical |= p
        boundary |= b
        unsafe |= event
        if event and first is None:
            first = float(row['time_s'])
    return {'unsafe': unsafe, 'physical_fall_observed': physical,
            'boundary_excursion_observed': boundary, 'first_unsafe_time_s': first,
            'termination_reason': 'physical_fall' if physical else 'terrain_boundary' if boundary else 'duration_complete'}


def enforce_substep_safety(metrics, rows):
    result = dict(metrics)
    result['numeric_gates'] = dict(metrics['numeric_gates'])
    result['substep_safety'] = substep_events(rows)
    if result['substep_safety']['unsafe']:
        for gate in ('A', 'progress'):
            if gate in result['numeric_gates']:
                result['numeric_gates'][gate] = False
    result['numeric_pass'] = all(result['numeric_gates'].values())
    return result


def exit_code(result):
    if result['status'] in ('ERROR', 'TIMEOUT', 'initializing'):
        return 1
    return 0 if result.get('numeric_pass') is True else 2


def recording_status(requested, result, metadata):
    performed = bool(requested and metadata and metadata.get('frames_per_view', 0) > 0)
    started = bool(performed and result.get('recording_started_before_first_physics_step') is True
                   and result.get('rows', 0) > 0)
    return {'recording_requested': bool(requested), 'recording_performed': performed,
            'recording_started_before_first_physics_step': started,
            'visual_gate_F': 'USER_REVIEW_PENDING' if performed else 'NOT_RECORDED'}
