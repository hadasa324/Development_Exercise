# Command and Control Application
## The application include the following files:
### Server files:
> 1. server.py
> 2. command_dir dirctory
>    - dowmload_from_url.py
>    - file_upload.py
>    - port_scan.py
>    - screenshot.py
>    - shell_exec.py
### Client files:
> 1. client.py
> 2. config_client_file.py

### To test this C2 Appliacation:
 Clone the repository:
```
https://github.com/hadasa324/Development_Exercise.git
```
Install the required python dependencies on both attacker and victim machines:
```
pip install -r requirements.txt
```
First run the server:
```
python server.py
```
 Then run the client:
```
python client.py
```
