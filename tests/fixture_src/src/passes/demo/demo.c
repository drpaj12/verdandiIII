/* Hand-made pass source for the locator tests; scanned, never compiled. */

static int demo_helper(int a) {
    return a + 1;
}

const odin3_pass_def odin3_pass_demo = {
    "demo",        "demo [--x]: does a demo",
    demo_pass_run, NULL,
    false,         ODIN3_PASS_PROCESSES_OK};

odin3_status demo_pass_run(odin3_pass_ctx *ctx, odin3_design *design, odin3_bytes args) {
    int n = demo_helper(1);
    odin3_log(ODIN3_LOG_DEBUG, "demo: module '%s': %s on %s '%s'",
              design->name, "rule", "type", "cell");
    (void)ctx;
    (void)args;
    (void)n;
    return ODIN3_OK;
}
