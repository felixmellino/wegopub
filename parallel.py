"""Run independent database reads at the same time.

Every database call costs a network round trip (~100 ms). Pages used to make
them one after another; calls that do not depend on each other can overlap, so
a page waits for the slowest one instead of the sum. Only use this for reads
that need nothing from each other.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx


def run_parallel(*calls):
    """Run zero-argument functions at once. Returns their results in the same order.
    If one fails, the others still finish and the first error (in call order) is raised."""
    if len(calls) <= 1:
        return [call() for call in calls]
    context = get_script_run_ctx()  # lets the workers use st.session_state like the page does

    def run(call):
        if context is not None:
            add_script_run_ctx(threading.current_thread(), context)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(run, call) for call in calls]
        return [future.result() for future in futures]
