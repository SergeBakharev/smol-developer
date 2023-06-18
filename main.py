import sys
import os
import ast
import logging
from time import sleep
from constants import DEFAULT_DIR, DEFAULT_MODEL, DEFAULT_MAX_TOKENS, EXTENSION_TO_SKIP

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_response(system_prompt, user_prompt, *args):
    import openai
    import tiktoken

    def reportTokens(prompt):
        encoding = tiktoken.encoding_for_model(DEFAULT_MODEL)
        # print number of tokens in light gray, with first 10 characters of prompt in green
        print(
            "\033[37m"
            + str(len(encoding.encode(prompt)))
            + " tokens\033[0m"
            + " in prompt: "
            + "\033[92m"
            + prompt[:50]
            + "\033[0m"
        )

    # Set up your OpenAI API credentials
    openai.api_key = os.environ["OPENAI_API_KEY"]

    messages = []
    messages.append({"role": "system", "content": system_prompt})
    reportTokens(system_prompt)
    messages.append({"role": "user", "content": user_prompt})
    reportTokens(user_prompt)
    # loop thru each arg and add it to messages alternating role between "assistant" and "user"
    role = "assistant"
    for value in args:
        messages.append({"role": role, "content": value})
        reportTokens(value)
        role = "user" if role == "assistant" else "assistant"

    params = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": 0,
    }

    # Send the API request
    keep_trying = True
    while keep_trying:
        try:
            response = openai.ChatCompletion.create(**params)
            keep_trying = False
        except Exception as e:
            # e.g. when the API is too busy, we don't want to fail everything
            print("Failed to generate response. Error: ", e)
            sleep(30)
            print("Retrying...")

    # Get the reply from the API response
    reply = response.choices[0]["message"]["content"]
    return reply


def generate_file(
    filename, filepaths_string=None, shared_dependencies=None, prompt=None
):
    # call openai api with this prompt
    filecode = generate_response(
        f"""You are an AI developer who is trying to write a program that will generate code for the user based on their intent.

    the app is: {prompt}

    the files we have decided to generate are: {filepaths_string}

    the shared dependencies (like filenames and variable names) we have decided on are: {shared_dependencies}

    only write valid code for the given filepath and file type, and return only the code.
    do not add any other explanation, only return valid code for that file type.
    """,
        f"""
    We have broken up the program into per-file generation.
    Now your job is to generate only the code for the file {filename}.
    Make sure to have consistent filenames if you reference other files we are also generating.

    Remember that you must obey 3 things:
       - you are generating code for the file {filename}
       - do not stray from the names of the files and the shared dependencies we have decided on
       - MOST IMPORTANT OF ALL - the purpose of our app is {prompt} - every line of code you generate must be valid code. Do not include code fences in your response, for example

    Bad response:
    ```javascript
    console.log("hello world")
    ```

    Good response:
    console.log("hello world")

    Begin generating the code now.

    """,
    )

    return filename, filecode


def main(prompt, directory=DEFAULT_DIR, file=None):
    # read file from prompt if it ends in a .md filetype
    if prompt.endswith(".md"):
        with open(prompt, "r") as promptfile:
            prompt = promptfile.read()

    print("hi its me, 🐣the smol developer🐣! you said you wanted:")
    # print the prompt in green color
    print("\033[92m" + prompt + "\033[0m")

    filelist_path = os.path.join(directory, 'filelist.txt')
    if not os.path.exists(filelist_path):

    # call openai api with this prompt
        filepaths_string = generate_response(
            """You are an AI developer who is trying to write a program that will generate code for the user based on their intent.

        When given their intent, create a complete, exhaustive list of filepaths that the user would write to make the program. Only list complete filepaths.

        Only list the filepaths you would write, and return them as a python list of strings separated by commas.
        Do not add any explanation or markup. Only return a list of filepaths in a python list format.

        good response:
        ["templates/index.html", "app.py"]

        bad response:
        templates/
            index.html

        """,
            prompt,
        )
        write_file("filelist.txt", filepaths_string, directory)
    else:
        with open(filelist_path, "r") as file:
            filepaths_string = file.read()
    is_good_list = input(f"The AI wants to make these files:\n{filepaths_string}\nLet it start?")
    if not is_good_list.lower().startswith("y"):
        print(f"List of files has been saved to: {filelist_path}. Edit this file manually to fine tune the files the AI will create.")
        exit()
    # parse the result into a python list
    list_actual = []
    try:
        list_actual = ast.literal_eval(filepaths_string)

        # if shared_dependencies.md is there, read it in, else set it to None
        shared_dependencies = None
        if os.path.exists("shared_dependencies.md"):
            with open("shared_dependencies.md", "r") as shared_dependencies_file:
                shared_dependencies = shared_dependencies_file.read()

        if file is not None:
            # check file
            print("file", file)
            filename, filecode = generate_file(
                file,
                filepaths_string=filepaths_string,
                shared_dependencies=shared_dependencies,
                prompt=prompt,
            )
            write_file(filename, filecode, directory)
        else:
            clean_dir(directory)

            # understand shared dependencies
            shared_dependencies = generate_response(
                """You are an AI developer who is trying to write a program that will generate code for the user based on their intent.

            In response to the user's prompt:

            ---
            the app is: {prompt}
            ---

            the files we have decided to generate are: {filepaths_string}

            Now that we have a list of files, we need to understand what dependencies they share.
            Please name and briefly describe what is shared between the files we are generating, including exported variables, data schemas, id names of every DOM elements that javascript functions will use, message names, and function names.
            Exclusively focus on the names of the shared dependencies, and do not add any other explanation.
            """,
                prompt,
            )
            print(shared_dependencies)
            # write shared dependencies as a md file inside the generated directory
            write_file("shared_dependencies.md", shared_dependencies, directory)

            for name in list_actual:
                filename, filecode = generate_file(
                    name,
                    filepaths_string=filepaths_string,
                    shared_dependencies=shared_dependencies,
                    prompt=prompt,
                )
                write_file(filename, filecode, directory)

    except ValueError as e:
        print("Failed to parse result: " + e)


def write_file(filename, filecode, directory):
    # Output the filename in blue color
    logging.debug("\033[94m" + filename + "\033[0m")
    logging.debug(f"contents: {filecode}")

    file_path = os.path.join(directory, filename)
    dir = os.path.dirname(file_path)
    os.makedirs(dir, exist_ok=True)

    if filename.endswith("/"):  # sometimes the model provides a folder without a file to create
        return

    # Open the file in write mode
    with open(file_path, "w") as file:
        # Write content to the file
        file.write(filecode)

def clean_dir(directory):
    # Check if the directory exists
    if os.path.exists(directory):
        # If it does, iterate over all files and directories
        for dirpath, _, filenames in os.walk(directory):
            for filename in filenames:
                _, extension = os.path.splitext(filename)
                if extension not in EXTENSION_TO_SKIP:
                    os.remove(os.path.join(dirpath, filename))
    else:
        os.makedirs(directory, exist_ok=True)

if __name__ == "__main__":

    # Check for arguments
    if len(sys.argv) < 2:

        # Looks like we don't have a prompt. Check if prompt.md exists
        if not os.path.exists("prompt.md"):

            # Still no? Then we can't continue
            print("Please provide a prompt")
            sys.exit(1)

        # Still here? Assign the prompt file name to prompt
        prompt = "prompt.md"

    else:
        # Set prompt to the first argument
        prompt = sys.argv[1]

    # Pull everything else as normal
    directory = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DIR
    file = sys.argv[3] if len(sys.argv) > 3 else None

    # Run the main function
    main(prompt, directory, file)
