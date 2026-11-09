#!/usr/bin/env python3
"""Purple's English Piper voice (libritts_r medium) with its randomness fixed, so noise_scale can give
s, z and f their hiss while the same text still sounds the same on every machine and every run.

Each RandomNormalLike in the model becomes one stored table of normal noise, repeated and cut to the
shape it was asked for. --half also stores the weights as float16, cast back as the model loads (half
the download, same math): Studio's copy.

Run once per voice change; the results are hosted on R2 and pinned in scripts/voice_model.sh, which
every build reads. Needs the onnx package (not one of Purple's dependencies):
    uv run --with onnx scripts/steady_voice.py <in.onnx> <out.onnx> [--half]
"""

import sys

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

CHANNELS, PERIOD, SEED = 192, 1024, 6006


def steady(model: onnx.ModelProto) -> onnx.ModelProto:
    g = model.graph
    table = np.random.default_rng(SEED).standard_normal((1, CHANNELS, PERIOD)).astype(np.float32)
    consts = {
        "steady/table": table,
        "steady/two": np.array(2, np.int64),
        "steady/period_less_one": np.array(PERIOD - 1, np.int64),
        "steady/period": np.array(PERIOD, np.int64),
        "steady/zero_axis": np.array([0], np.int64),
        "steady/ones": np.array([1, 1], np.int64),
        "steady/starts": np.array([0, 0, 0], np.int64),
    }
    g.initializer.extend(numpy_helper.from_array(v, k) for k, v in consts.items())
    nodes = []
    for n in g.node:
        if n.op_type != "RandomNormalLike":
            nodes.append(n)
            continue
        p = f"steady{n.name}"
        nodes += [
            helper.make_node("Shape", [n.input[0]], [f"{p}/shape"]),
            helper.make_node("Gather", [f"{p}/shape", "steady/two"], [f"{p}/length"]),
            helper.make_node("Add", [f"{p}/length", "steady/period_less_one"], [f"{p}/rounded"]),
            helper.make_node("Div", [f"{p}/rounded", "steady/period"], [f"{p}/times"]),
            helper.make_node("Unsqueeze", [f"{p}/times", "steady/zero_axis"], [f"{p}/times1"]),
            helper.make_node("Concat", ["steady/ones", f"{p}/times1"], [f"{p}/repeats"], axis=0),
            helper.make_node("Tile", ["steady/table", f"{p}/repeats"], [f"{p}/tiled"]),
            helper.make_node("Slice", [f"{p}/tiled", "steady/starts", f"{p}/shape"], [n.output[0]]),
        ]
    del g.node[:]
    g.node.extend(nodes)
    return model


def half(model: onnx.ModelProto) -> onnx.ModelProto:
    g = model.graph
    weights, casts = [], []
    for init in g.initializer:
        if init.data_type == TensorProto.FLOAT and np.prod(init.dims) > 64:
            stored = numpy_helper.from_array(numpy_helper.to_array(init).astype(np.float16), f"{init.name}/half")
            weights.append(stored)
            casts.append(helper.make_node("Cast", [stored.name], [init.name], to=TensorProto.FLOAT))
        else:
            weights.append(init)
    del g.initializer[:]
    g.initializer.extend(weights)
    nodes = list(g.node)
    del g.node[:]
    g.node.extend(casts + nodes)
    return model


if __name__ == "__main__":
    model = steady(onnx.load(sys.argv[1]))
    if "--half" in sys.argv[3:]:
        model = half(model)
    onnx.checker.check_model(model)
    onnx.save(model, sys.argv[2])
