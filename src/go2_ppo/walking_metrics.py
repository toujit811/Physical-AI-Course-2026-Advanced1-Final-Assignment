"""Fixed Stage 1 acceptance: no early distance-only success."""


def classify(elapsed, distance, fallen, engine_error, config):
    if engine_error:
        return "engine_error"
    if fallen:
        return "fallen"
    if elapsed < config["duration_s"]-1e-8:
        return "incomplete"
    if distance < config["target_distance_m"]:
        return "insufficient_distance"
    return "passed"
