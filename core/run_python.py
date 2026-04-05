import subprocess
import os


def run_python_script(script_name):

    script_name = script_name.strip()

    if not script_name:

        return "Please specify a Python script"

    if not script_name.endswith(".py"):

        script_name += ".py"

    if not os.path.exists(script_name):

        return f"Script not found: {script_name}"

    try:

        result = subprocess.run(
            ["python", script_name],
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout.strip()

        error = result.stderr.strip()

        if error:

            return f"Error:\n{error}"

        if output:

            return output

        return "Script executed successfully"

    except subprocess.TimeoutExpired:

        return "Script execution timed out"

    except Exception as e:

        return f"Execution failed: {str(e)}"