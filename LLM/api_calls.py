import requests
import json
from LLM.config import ANTHROPIC_API_KEY


def build_prompt(request_constraint):
    # Set up the file paths
    file_paths = {
        "integer_program": "Zone_Generation/integer_program_abstract.py",
        "units_data": "LLM/Data_Description/units_data.txt",
        "units_data_5_rows": "LLM/Data_Description/units_data_5_rows.csv",
        "latex_formula": "LLM/Data_Description/latex_formula.txt"
    }
    # Read the contents of the files
    file_contents = {}
    for file in file_paths:
        with open(file_paths[file], "r") as data:
            file_contents[file] = data.read()

    output_format = {
        'Function_Code': '''
         only only only the code for the function that was requested. start and end the value, which is a function, with three single quotes, 
         and keep the double quotes for any other strings inside the code. 
        ''',
        'Latex_Formula': {
            'Variables': {
                'A': "Definition of the new variable A, in the formula (if any new variables are defined)",
                'B': "Definition of the new variable B, in the formula (if any new variables are defined)",
            },
            'Formula': 'Theoretical Latex formula, for the constraint that was requested. '
                       'Dont make any changes to the original forumal. Dont use \\'
        }
    }
    output_format = json.dumps(output_format, indent=2)

    example_request_function = """ 
    Write a function in python to make sure each zone has at least 2 of the top 10 schools.
     To find top 10 schools, Sort schools by their quality, using an average color index. """

    example_expexcted_output_by_claude = {
        'Function_Code': """
    def requested_function(self):
        color_scores = self.units_data["AvgColorIndex"].fillna(value=0)
        top_schools = np.zeros([self.U])
        top = np.percentile(color_scores, 100 * (1 - 10 / self.U))
        for u in range(self.U):
           if color_scores[u] > top:
               top_schools[u] = 1
        for z in range(self.Z):
           topz = gp.quicksum(
               [self.x[v, z] * top_schools[v] for v in self.valid_units_per_zone[z]]
           )
           self.m.addConstr(topz >= 2)
    """,
        'Latex_Formula': {
            'Variables': {
                'top_schools_u': 'A binary variable indicating if unit u is among the top 10 schools based on the average color index',
            },
            'Formula': '\sum_{u \in U[z]} x_{u,z} \cdot top_schools_u \geq 2 \quad \forall z \in [Z]'
        }
    }

    # request_constraint = """
    # Write a function in python to make sure the average school quality across zones is within 20% deviation.
    #  Use Math Score at school level to compute school quality."""

    api_prompt = f"""
    Here are the files:

    File integer_program.py: {file_contents["integer_program"]}

    File units_data.txt: {file_contents["units_data"]}

    File units_data_5_rows.csv: {file_contents["units_data_5_rows"]}

    latex_formula.txt: {file_contents["latex_formula"]}

    Project Description: 
    In partnership with SFUSD (San Francisco Unified School District), I've developed a solution,
    to find a zoning system for schools. Where we divide the city of San Francisco, into a number of zones (i.e. a number between 2 to 25).
    The generated solutions should be balanced within a given range, for specific quality or capacity metrics.

    Census units: Building blocks of the city. Each census unit should be assigned to exactly one zone.
                  Variable self.x[u,z]: is a binary variable. It indicates whether unit u is assigned to zone z or not.
    You can access units using their index: For each value u in range(self.U), there is a unique unit, with index u.
                            In other words, each value u in [0,..., self.U], represents a different unit.

    Number of zones: self.Z. Number of zones that we are trying to divide the city into.

    Zone Description: 
    - Each zone, consists of a set of census units.
    - To compute a zone metric we aggregate the corresponding metric for all census units, assigned to that zone. 
        Example: Total number of students in zone z = sum of students among all census units assigned to zone z. 
    - Zones should have limited shortage: Shortage is the percentage of extra number of GE students in each zone compared to total number of GE seats within that zone. 
        Zone should not have shortage more than max_shortage percentage, where max_shortage is a given input. 
    - Zones should be contiguous, and not to be consisting of multiple islands. 
    - Zones should be nicely shaped and compact looking.

    We use Gurobi for linear programming to impose the desired constraints. I attached the code that generates zone constraints.
    I want you to fully read and understand the code and the data structures used within the code.
    Then, help me add the new request_constraint: {request_constraint} to the existing model.


    Instructions:
    1. Please thoroughly analyze the code in integer_program.py, 
        pay close attention to the data structures and code organization, by reading the comments.
    2. Aim to deeply understand integer_program.py and its functionality, 
        and how I implemented the integer programming constraints.
    4. self.units_data dataframe: 
        - Each row of self.units_data is a different unit. Row i, has information about unit with index i.
        - Head 5 rows of self.units_data dataframe are saved in units_data_5_rows.csv. 
        - Meaning of columns in self.units_data dataframe is saved in units_data.txt. 
        - Make sure you understand the units_data dataframe by reading the content of units_data.txt and looking at units_data.csv.
    5. Data structures in integer_program.py are explained in the code comments in integer_program.py file.

    Code Generation Instructions: 
    1. Write a function in python to make sure request_constraint is satisfied. 
    2. Very important: Ensure your suggested code function can be appended to the existing 
        code file exactly the way you provide it, without causing any conflicts or errors.
         Make sure your proposed function is compatible with the existing data structures in integer_program.py
    3. Format: A Python code in standard format. The code should be formatted in a way that can be directly copy-pasted and appended to the existing file.
    4. Only return a python code, without any explanation. Your output should be only a python function, named: requested_function, with no input arguments
        If you have anything you really need to say, put it in code comments.

    Latex Generation Instructions: 
    1. Go thoroughly through latex_formula.txt. The latex formula for every constraint that is already imposed is included in the latex_formula.txt. 
    2. Understand latex_formula.txt to learn how to formulate and write the latex formula for a given provided constraint.
    3. Return the correct theoretical Latex formula, for the new request_constraint. 
    4. Make sure your latex formula compiles with latex compiler
    5. Define only only variables that have not been yet defined in latex_formula.txt. If you are using any of the 
        variables already defined in latex_formula.txt, you don't need to define them again



    Your output should have the exact following json format, with no additional text besides outside of this format:
    output_format: {output_format}

    Here is an Example to learn from: 
    Example Desired Constraint: {example_request_function}
    Example Expected output from you: {example_expexcted_output_by_claude}

    Make sure:
    1- Your function directly runs when appended to the existing project.
    2- Your latext formula runs correctly when using a Latex compiler.
    3- Return only only only a json in the output_format and nothing else
    """
    return api_prompt


def make_api_call(request_constraint):


    API_URL = "https://api.anthropic.com/v1/messages"

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    api_prompt = build_prompt(request_constraint)

    data = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": api_prompt}
        ]
    }

    response = requests.post(API_URL, headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        print("text: ", result["content"][0]['text'])
        return result["content"][0]['text']
    else:
        print(f"Error: {response.status_code} - {response.text}")


if __name__ == "__main__":
    print("Calling Claude")
    request_constraint = ("Write a function in python to make sure the average school"
                          " quality across zones is within 20% deviation. Use Math Score "
                          "at school level to compute school quality.")
    llm_response = make_api_call(request_constraint)


    request_constraint: """
    Write a function in python to make sure: Fraction of Hispanic students
    across all zones is balanced, and has maximum 20% deviation across zones."""
    #
    # request_constraint: """
    # Write a function in python to make sure:
    # average quality of schools across zones is balanced.
    # Use average color index to measure school quality."""
    #
    # request_constraint: """
    # Write a function in python to make sure: Fraction of students at the school across all zones that meet
    # grade level standards is about the same, and is within 10% deviation.
    # """