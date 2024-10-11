import os
import sys
import logging
from datetime import datetime
from .driver import submit
from driver_library_{{ org_name }}_{{ venture_name }}.driver_library.utils.core.environment import CheckEnvironment

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(lineno)d: %(message)s')


class Constants:
    # per job parameters
    docker_variables = ["from_date", "to_date", "form_type"]

    optional_docker_variables = ["cik", "ticker", "cik_array"]

    # cloud parameters (from kubernetes secrets)
    secret_variables = ["AWS_ACCESS_KEY", "AWS_SECRET_KEY", "AWS_REGION"]

    # configuration parameters
    configuration_variables = ["bucket", "user_agent", "scheduled_from_date", "scheduled_form_type"]


def parse_date(date_time_value: str) -> str:

    if not date_time_value:
        raise ValueError("Date was not supplied.")

    try:

        logger.info(f'original date = {date_time_value}')
        dt = date_time_value.split()[0]
        logger.info(f'date portion = {dt}')

        obj = datetime.strptime(dt, "%Y-%m-%d")
        # Return the date portion as a string
        rc = obj.strftime("%Y-%m-%d")

        logger.info(f'validated date = {rc}')

        return rc

    except ValueError:
        raise ValueError(f"Supplied date [{date_time_value}] has incorrect format.")


def fix_scheduled_inputs(args: dict, env_vars: dict) -> dict:

    if args["scheduled"]:

        logger.info("scheduled run - will take certain parameters from config map")

        # fix up certain parameters
        args["form_type"] = env_vars["scheduled_form_type"]

        logger.info(f"scheduled run - form_type = {args['form_type']} from config map")
        logger.info(f"checking input start date {args['from_date']}")
        logger.info(f"checking config map start date = {env_vars['scheduled_from_date']}")

        if args["from_date"].casefold() == "None".casefold():

            logger.info("scheduled run - 1st run detected")
            args["from_date"] = env_vars["scheduled_from_date"]
            logger.info(f"scheduled run - from_date = {args['from_date']} from config map")

    else:
        logger.info("manual run - scheduled parameters are ignored")

    logger.info(f'fix_scheduled_inputs return {args}')
    return args


def get_edgar_inputs(args: dict, env_vars: dict) -> dict:
    args_dict = {}

    for key in Constants.docker_variables:
        args_dict[key] = args[key]
        logger.info(f"Found variable {key} = [{args_dict[key]}] .")

    for key in Constants.optional_docker_variables:
        if args.get(key) is not None:
            args_dict[key] = args.get(key)
            logger.info(f"Found optional variable {key} = [{args_dict[key]}] .")

    args_dict = fix_scheduled_inputs(args, env_vars)

    # parse date format
    args_dict["from_date"] = parse_date(args_dict["from_date"])
    args_dict["to_date"] = parse_date(args_dict["to_date"])

    logger.info(f'get_edgar_inputs return {args_dict}')
    return args_dict


def run(args: dict) -> dict:
    """
    Main entry point into edgar driver called from Airflow DAG.
    :param args: args is a dictionary with all inputs needed to run the program
    :return: return value is a dictionary with all outputs (s3 location in this case)
    """

    if args["scheduled"]:
        logger.info(f"Edgar - started - scheduled run.")
    else:
        logger.info(f"Edgar - started - manual run.")

    logger.info(f'input args = {args}')

    env_vars = CheckEnvironment.get_env(Constants.secret_variables + Constants.configuration_variables)

    logger.info(f'env vars = {env_vars}')

    if not CheckEnvironment.check_keys(Constants.secret_variables + Constants.configuration_variables, env_vars):
        logger.error(f"Required environment variables for edgar are not present.")
        sys.exit(1)

    if not CheckEnvironment.check_keys(Constants.docker_variables, args):
        logger.error(f"Required variables for edgar are not present.")
        sys.exit(1)

    args_dict = get_edgar_inputs(args, env_vars)

    all_vars = {**args_dict, **env_vars}

    rc = submit(all_vars)

    logger.info(f"Edgar - completed.")

    return rc


