import copy
import json
import logging
import unittest
from datetime import datetime
from datetime import timedelta
from queue import Queue
from unittest import mock

import pika

from src.data_store.redis import RedisApi
from src.data_transformers.node.chainlink import ChainlinkNodeDataTransformer
from src.message_broker.rabbitmq import RabbitMQApi
from src.monitorables.nodes.chainlink_node import ChainlinkNode
from src.utils import env
from src.utils.constants.rabbitmq import (
    HEALTH_CHECK_EXCHANGE, RAW_DATA_EXCHANGE, STORE_EXCHANGE, ALERT_EXCHANGE,
    CL_NODE_DT_INPUT_QUEUE_NAME, CHAINLINK_NODE_RAW_DATA_ROUTING_KEY,
    HEARTBEAT_OUTPUT_WORKER_ROUTING_KEY)
from src.utils.exceptions import (PANICException, NodeIsDownException)
from test.utils.utils import (connect_to_rabbit, disconnect_from_rabbit,
                              delete_exchange_if_exists, delete_queue_if_exists,
                              save_chainlink_node_to_redis)


class TestChainlinkNodeDataTransformer(unittest.TestCase):
    def setUp(self) -> None:
        # Some dummy data
        self.test_data_str = 'test_data'
        self.transformer_name = 'test_chainlink_node_data_transformer'
        self.max_queue_size = 1000
        self.test_publishing_queue = Queue(self.max_queue_size)
        self.test_rabbit_queue_name = 'Test Queue'
        self.test_last_monitored = datetime(2012, 1, 1).timestamp()
        self.test_heartbeat = {
            'component_name': 'Test Component',
            'is_alive': True,
            'timestamp': self.test_last_monitored,
        }
        self.test_exception = PANICException('test_exception', 1)
        self.dummy_logger = logging.getLogger('Dummy')
        self.dummy_logger.disabled = True
        self.invalid_transformed_data = {'bad_key': 'bad_value'}
        self.test_monitor_name = 'test_monitor_name'

        # Rabbit instance
        self.connection_check_time_interval = timedelta(seconds=0)
        self.rabbit_ip = env.RABBIT_IP
        self.rabbitmq = RabbitMQApi(
            self.dummy_logger, self.rabbit_ip,
            connection_check_time_interval=self.connection_check_time_interval)

        # Redis Instance
        self.redis_db = env.REDIS_DB
        self.redis_host = env.REDIS_IP
        self.redis_port = env.REDIS_PORT
        self.redis_namespace = env.UNIQUE_ALERTER_IDENTIFIER
        self.redis = RedisApi(self.dummy_logger, self.redis_db,
                              self.redis_host, self.redis_port, '',
                              self.redis_namespace,
                              self.connection_check_time_interval)

        # Some dummy state
        self.test_chainlink_node_name = 'test_chainlink_node'
        self.test_chainlink_node_id = 'test_chainlink_node_id345834t8h3r5893h8'
        self.test_chainlink_node_parent_id = 'test_chainlink_node_parent_id34fg'
        self.test_chainlink_node = ChainlinkNode(
            self.test_chainlink_node_name, self.test_chainlink_node_id,
            self.test_chainlink_node_parent_id)
        self.test_node_is_down_exception = NodeIsDownException(
            self.test_chainlink_node.node_name)
        self.test_state = {
            self.test_chainlink_node_id: self.test_chainlink_node
        }
        self.test_went_down_at = 45.4
        self.test_current_height = 50000000000
        self.test_eth_blocks_in_queue = 3
        self.test_total_block_headers_received = 454545040
        self.test_total_block_headers_dropped = 4
        self.test_no_of_active_jobs = 10
        self.test_max_pending_tx_delay = 6
        self.test_process_start_time_seconds = 345474.4
        self.test_total_gas_bumps = 11
        self.test_total_gas_bumps_exceeds_limit = 13
        self.test_no_of_unconfirmed_txs = 7
        self.test_total_errored_job_runs = 15
        self.test_current_gas_price_info = {
            'percentile': 50.5,
            'price': 22,
        }
        self.test_eth_balance_info = {
            'address1': {'balance': 34.4, 'latest_usage': 5.0},
            'address2': {'balance': 40.0, 'latest_usage': 0.0},
            'address3': {'balance': 70.0, 'latest_usage': 34.0}
        }
        self.test_last_prometheus_source_used = "prometheus_source_1"
        self.test_last_monitored_prometheus = 45.666786
        self.test_chainlink_node.set_went_down_at(self.test_went_down_at)
        self.test_chainlink_node.set_current_height(self.test_current_height)
        self.test_chainlink_node.set_eth_blocks_in_queue(
            self.test_eth_blocks_in_queue)
        self.test_chainlink_node.set_total_block_headers_received(
            self.test_total_block_headers_received)
        self.test_chainlink_node.set_total_block_headers_dropped(
            self.test_total_block_headers_dropped)
        self.test_chainlink_node.set_no_of_active_jobs(
            self.test_no_of_active_jobs)
        self.test_chainlink_node.set_max_pending_tx_delay(
            self.test_max_pending_tx_delay)
        self.test_chainlink_node.set_process_start_time_seconds(
            self.test_process_start_time_seconds)
        self.test_chainlink_node.set_total_gas_bumps(self.test_total_gas_bumps)
        self.test_chainlink_node.set_total_gas_bumps_exceeds_limit(
            self.test_total_gas_bumps_exceeds_limit)
        self.test_chainlink_node.set_no_of_unconfirmed_txs(
            self.test_no_of_unconfirmed_txs)
        self.test_chainlink_node.set_total_errored_job_runs(
            self.test_total_errored_job_runs)
        self.test_chainlink_node.set_current_gas_price_info(
            self.test_current_gas_price_info['percentile'],
            self.test_current_gas_price_info['price'])
        self.test_chainlink_node.set_eth_balance_info(
            self.test_eth_balance_info)
        self.test_chainlink_node.set_last_prometheus_source_used(
            self.test_last_prometheus_source_used)
        self.test_chainlink_node.set_last_monitored_prometheus(
            self.test_last_monitored_prometheus)

        # Loading objects
        self.loaded_cl_node_default_data = ChainlinkNode(
            self.test_chainlink_node_name, self.test_chainlink_node_id,
            self.test_chainlink_node_parent_id)
        self.loaded_cl_node_trans_data = ChainlinkNode(
            self.test_chainlink_node_name, self.test_chainlink_node_id,
            self.test_chainlink_node_parent_id)
        self.loaded_cl_node_trans_data.set_went_down_at(self.test_went_down_at)
        self.loaded_cl_node_trans_data.set_current_height(
            self.test_current_height)
        self.loaded_cl_node_trans_data.set_eth_blocks_in_queue(
            self.test_eth_blocks_in_queue)
        self.loaded_cl_node_trans_data.set_total_block_headers_received(
            self.test_total_block_headers_received)
        self.loaded_cl_node_trans_data.set_total_block_headers_dropped(
            self.test_total_block_headers_dropped)
        self.loaded_cl_node_trans_data.set_no_of_active_jobs(
            self.test_no_of_active_jobs)
        self.loaded_cl_node_trans_data.set_max_pending_tx_delay(
            self.test_max_pending_tx_delay)
        self.loaded_cl_node_trans_data.set_process_start_time_seconds(
            self.test_process_start_time_seconds)
        self.loaded_cl_node_trans_data.set_total_gas_bumps(
            self.test_total_gas_bumps)
        self.loaded_cl_node_trans_data.set_total_gas_bumps_exceeds_limit(
            self.test_total_gas_bumps_exceeds_limit)
        self.loaded_cl_node_trans_data.set_no_of_unconfirmed_txs(
            self.test_no_of_unconfirmed_txs)
        self.loaded_cl_node_trans_data.set_total_errored_job_runs(
            self.test_total_errored_job_runs)
        self.loaded_cl_node_trans_data.set_current_gas_price_info(
            self.test_current_gas_price_info['percentile'],
            self.test_current_gas_price_info['price'])
        self.loaded_cl_node_trans_data.set_eth_balance_info(
            self.test_eth_balance_info)
        self.loaded_cl_node_trans_data.set_last_prometheus_source_used(
            self.test_last_prometheus_source_used)
        self.loaded_cl_node_trans_data.set_last_monitored_prometheus(
            self.test_last_monitored_prometheus)
        self.test_chainlink_node_new = ChainlinkNode(
            self.test_chainlink_node_name, self.test_chainlink_node_id,
            self.test_chainlink_node_parent_id)
        self.test_went_down_at_new = None
        self.test_current_height_new = 50000000001
        self.test_eth_blocks_in_queue_new = 4
        self.test_total_block_headers_received_new = 454545041
        self.test_total_block_headers_dropped_new = 5
        self.test_no_of_active_jobs_new = 11
        self.test_max_pending_tx_delay_new = 7
        self.test_process_start_time_seconds_new = 345476.4
        self.test_total_gas_bumps_new = 13
        self.test_total_gas_bumps_exceeds_limit_new = 14
        self.test_no_of_unconfirmed_txs_new = 8
        self.test_total_errored_job_runs_new = 16
        self.test_current_gas_price_info_new = {
            'percentile': 52.5,
            'price': 24,
        }
        self.test_eth_balance_info_new = {
            'address1': {'balance': 44.4, 'latest_usage': 6.0},
            'address2': {'balance': 45.0, 'latest_usage': 2.0},
            'address3': {'balance': 76.0, 'latest_usage': 0.0},
            'address4': {'balance': 67.0, 'latest_usage': 0.0}
        }
        self.test_last_prometheus_source_used_new = "prometheus_source_2"
        self.test_last_monitored_prometheus_new = 47.666786
        self.test_chainlink_node_new.set_went_down_at(
            self.test_went_down_at_new)
        self.test_chainlink_node_new.set_current_height(
            self.test_current_height_new)
        self.test_chainlink_node_new.set_eth_blocks_in_queue(
            self.test_eth_blocks_in_queue_new)
        self.test_chainlink_node_new.set_total_block_headers_received(
            self.test_total_block_headers_received_new)
        self.test_chainlink_node_new.set_total_block_headers_dropped(
            self.test_total_block_headers_dropped_new)
        self.test_chainlink_node_new.set_no_of_active_jobs(
            self.test_no_of_active_jobs_new)
        self.test_chainlink_node_new.set_max_pending_tx_delay(
            self.test_max_pending_tx_delay_new)
        self.test_chainlink_node_new.set_process_start_time_seconds(
            self.test_process_start_time_seconds_new)
        self.test_chainlink_node_new.set_total_gas_bumps(
            self.test_total_gas_bumps_new)
        self.test_chainlink_node_new.set_total_gas_bumps_exceeds_limit(
            self.test_total_gas_bumps_exceeds_limit_new)
        self.test_chainlink_node_new.set_no_of_unconfirmed_txs(
            self.test_no_of_unconfirmed_txs_new)
        self.test_chainlink_node_new.set_total_errored_job_runs(
            self.test_total_errored_job_runs_new)
        self.test_chainlink_node_new.set_current_gas_price_info(
            self.test_current_gas_price_info_new['percentile'],
            self.test_current_gas_price_info_new['price'])
        self.test_chainlink_node_new.set_eth_balance_info(
            self.test_eth_balance_info_new)
        self.test_chainlink_node_new.set_last_prometheus_source_used(
            self.test_last_prometheus_source_used_new)
        self.test_chainlink_node_new.set_last_monitored_prometheus(
            self.test_last_monitored_prometheus_new)

        # Transformed data examples
        self.transformed_data_example_result_all = {
            'prometheus': {
                'result': {
                    'meta_data': {
                        'monitor_name': self.test_monitor_name,
                        'node_name': self.test_chainlink_node_name,
                        'last_source_used':
                            self.test_last_prometheus_source_used_new,
                        'node_id': self.test_chainlink_node_id,
                        'node_parent_id': self.test_chainlink_node_parent_id,
                        'last_monitored':
                            self.test_last_monitored_prometheus_new,
                    },
                    'data': {
                        'went_down_at': self.test_went_down_at_new,
                        'current_height': self.test_current_height_new,
                        'eth_blocks_in_queue':
                            self.test_eth_blocks_in_queue_new,
                        'total_block_headers_received':
                            self.test_total_block_headers_received_new,
                        'total_block_headers_dropped':
                            self.test_total_block_headers_dropped_new,
                        'no_of_active_jobs': self.test_no_of_active_jobs_new,
                        'max_pending_tx_delay':
                            self.test_max_pending_tx_delay_new,
                        'process_start_time_seconds':
                            self.test_process_start_time_seconds_new,
                        'total_gas_bumps': self.test_total_gas_bumps_new,
                        'total_gas_bumps_exceeds_limit':
                            self.test_total_gas_bumps_exceeds_limit_new,
                        'no_of_unconfirmed_txs':
                            self.test_no_of_unconfirmed_txs_new,
                        'total_errored_job_runs':
                            self.test_total_errored_job_runs_new,
                        'current_gas_price_info':
                            self.test_current_gas_price_info_new,
                        'eth_balance_info': self.test_eth_balance_info_new,
                    },
                }
            }
        }
        self.transformed_data_example_result_options_None = copy.deepcopy(
            self.transformed_data_example_result_all)
        self.transformed_data_example_result_options_None['prometheus'][
            'result']['data']['current_gas_price_info'] = None
        self.transformed_data_example_general_error = {
            'prometheus': {
                'error': {
                    'meta_data': {
                        'monitor_name': self.test_monitor_name,
                        'node_name': self.test_chainlink_node_name,
                        'last_source_used':
                            self.test_last_prometheus_source_used_new,
                        'node_id': self.test_chainlink_node_id,
                        'node_parent_id': self.test_chainlink_node_parent_id,
                        'time': self.test_last_monitored_prometheus_new
                    },
                    'message': self.test_exception.message,
                    'code': self.test_exception.code,
                }
            }
        }
        self.transformed_data_example_downtime_error = {
            'prometheus': {
                'error': {
                    'meta_data': {
                        'monitor_name': self.test_monitor_name,
                        'node_name': self.test_chainlink_node_name,
                        'last_source_used':
                            self.test_last_prometheus_source_used_new,
                        'node_id': self.test_chainlink_node_id,
                        'node_parent_id': self.test_chainlink_node_parent_id,
                        'time': self.test_last_monitored_prometheus_new
                    },
                    'message': self.test_node_is_down_exception.message,
                    'code': self.test_node_is_down_exception.code,
                    'data': {
                        'went_down_at': self.test_last_monitored_prometheus_new
                    }
                }
            }
        }

        # Test transformer
        self.test_data_transformer = ChainlinkNodeDataTransformer(
            self.transformer_name, self.dummy_logger, self.redis, self.rabbitmq,
            self.max_queue_size)

    def tearDown(self) -> None:
        # Delete any queues and exchanges which are common across many tests
        connect_to_rabbit(self.test_data_transformer.rabbitmq)
        delete_queue_if_exists(self.test_data_transformer.rabbitmq,
                               CL_NODE_DT_INPUT_QUEUE_NAME)
        delete_exchange_if_exists(self.test_data_transformer.rabbitmq,
                                  HEALTH_CHECK_EXCHANGE)
        delete_exchange_if_exists(self.test_data_transformer.rabbitmq,
                                  RAW_DATA_EXCHANGE)
        delete_exchange_if_exists(self.test_data_transformer.rabbitmq,
                                  STORE_EXCHANGE)
        delete_exchange_if_exists(self.test_data_transformer.rabbitmq,
                                  ALERT_EXCHANGE)
        disconnect_from_rabbit(self.test_data_transformer.rabbitmq)

        self.dummy_logger = None
        self.connection_check_time_interval = None
        self.rabbitmq = None
        self.redis = None
        self.test_node_is_down_exception = None
        self.test_exception = None
        self.test_chainlink_node = None
        self.test_chainlink_node_new = None
        self.test_state = None
        self.test_publishing_queue = None
        self.test_last_monitored = None
        self.test_heartbeat = None
        self.invalid_transformed_data = None
        self.test_data_transformer = None
        self.loaded_cl_node_default_data = None
        self.loaded_cl_node_trans_data = None
        self.transformed_data_example_result_all = None
        self.transformed_data_example_result_options_None = None
        self.transformed_data_example_general_error = None
        self.transformed_data_example_downtime_error = None

    def test_str_returns_transformer_name(self) -> None:
        self.assertEqual(self.transformer_name, str(self.test_data_transformer))

    def test_transformer_name_returns_transformer_name(self) -> None:
        self.assertEqual(self.transformer_name,
                         self.test_data_transformer.transformer_name)

    def test_redis_returns_transformer_redis_instance(self) -> None:
        self.assertEqual(self.redis, self.test_data_transformer.redis)

    def test_state_returns_the_systems_state(self) -> None:
        self.test_data_transformer._state = self.test_state
        self.assertEqual(self.test_state, self.test_data_transformer.state)

    def test_publishing_queue_returns_publishing_queue(self) -> None:
        self.test_data_transformer._publishing_queue = \
            self.test_publishing_queue
        self.assertEqual(self.test_publishing_queue,
                         self.test_data_transformer.publishing_queue)

    def test_publishing_queue_has_the_correct_max_size(self) -> None:
        self.assertEqual(self.max_queue_size,
                         self.test_data_transformer.publishing_queue.maxsize)

    @mock.patch.object(RabbitMQApi, "start_consuming")
    def test_listen_for_data_calls_start_consuming(
            self, mock_start_consuming) -> None:
        mock_start_consuming.return_value = None
        self.test_data_transformer._listen_for_data()
        mock_start_consuming.assert_called_once()

    @mock.patch.object(RabbitMQApi, "basic_qos")
    def test_initialise_rabbit_initializes_everything_as_expected(
            self, mock_basic_qos) -> None:
        # To make sure that there is no connection/channel already established
        self.assertIsNone(self.rabbitmq.connection)
        self.assertIsNone(self.rabbitmq.channel)

        # To make sure that the exchanges and queues have not already been
        # declared
        connect_to_rabbit(self.rabbitmq)
        self.test_data_transformer.rabbitmq.queue_delete(
            CL_NODE_DT_INPUT_QUEUE_NAME)
        self.test_data_transformer.rabbitmq.exchange_delete(
            HEALTH_CHECK_EXCHANGE)
        self.test_data_transformer.rabbitmq.exchange_delete(RAW_DATA_EXCHANGE)
        self.test_data_transformer.rabbitmq.exchange_delete(STORE_EXCHANGE)
        self.test_data_transformer.rabbitmq.exchange_delete(ALERT_EXCHANGE)
        self.rabbitmq.disconnect()

        self.test_data_transformer._initialise_rabbitmq()

        # Perform checks that the connection has been opened and marked as open,
        # that the delivery confirmation variable is set and basic_qos called
        # successfully.
        self.assertTrue(self.test_data_transformer.rabbitmq.is_connected)
        self.assertTrue(self.test_data_transformer.rabbitmq.connection.is_open)
        self.assertTrue(
            self.test_data_transformer.rabbitmq.channel._delivery_confirmation)
        mock_basic_qos.assert_called_once_with(
            prefetch_count=round(self.max_queue_size / 5))

        # Check whether the producing exchanges have been created by using
        # passive=True. If this check fails an exception is raised
        # automatically.
        self.test_data_transformer.rabbitmq.exchange_declare(STORE_EXCHANGE,
                                                             passive=True)
        self.test_data_transformer.rabbitmq.exchange_declare(ALERT_EXCHANGE,
                                                             passive=True)
        self.test_data_transformer.rabbitmq.exchange_declare(
            HEALTH_CHECK_EXCHANGE, passive=True)

        # Check whether the consuming exchanges and queues have been creating by
        # sending messages with the same routing keys as for the bindings. We
        # will also check if the size of the queues is 0 to confirm that
        # basic_consume was called (it will store the msg in the component
        # memory immediately). If one of the exchanges or queues is not created
        # or basic_consume is not called, then either an exception will be
        # thrown or the queue size would be 1 respectively. Note when deleting
        # the exchanges in the beginning we also released every binding, hence
        # there is no other queue binded with the same routing key to any
        # exchange at this point.
        self.test_data_transformer.rabbitmq.basic_publish_confirm(
            exchange=RAW_DATA_EXCHANGE,
            routing_key=CHAINLINK_NODE_RAW_DATA_ROUTING_KEY,
            body=self.test_data_str, is_body_dict=False,
            properties=pika.BasicProperties(delivery_mode=2), mandatory=True)

        # Re-declare queue to get the number of messages
        res = self.test_data_transformer.rabbitmq.queue_declare(
            CL_NODE_DT_INPUT_QUEUE_NAME, False, True, False, False)
        self.assertEqual(0, res.method.message_count)

    def test_send_heartbeat_sends_a_heartbeat_correctly(self) -> None:
        # This test creates a queue which receives messages with the same
        # routing key as the ones set by send_heartbeat, and checks that the
        # heartbeat is received
        self.test_data_transformer._initialise_rabbitmq()

        # Delete the queue before to avoid messages in the queue on error.
        self.test_data_transformer.rabbitmq.queue_delete(
            self.test_rabbit_queue_name)

        res = self.test_data_transformer.rabbitmq.queue_declare(
            queue=self.test_rabbit_queue_name, durable=True, exclusive=False,
            auto_delete=False, passive=False
        )
        self.assertEqual(0, res.method.message_count)
        self.test_data_transformer.rabbitmq.queue_bind(
            queue=self.test_rabbit_queue_name, exchange=HEALTH_CHECK_EXCHANGE,
            routing_key=HEARTBEAT_OUTPUT_WORKER_ROUTING_KEY)

        self.test_data_transformer._send_heartbeat(self.test_heartbeat)

        # By re-declaring the queue again we can get the number of messages
        # in the queue.
        res = self.test_data_transformer.rabbitmq.queue_declare(
            queue=self.test_rabbit_queue_name, durable=True, exclusive=False,
            auto_delete=False, passive=True
        )
        self.assertEqual(1, res.method.message_count)

        # Check that the message received is actually the HB
        _, _, body = self.test_data_transformer.rabbitmq.basic_get(
            self.test_rabbit_queue_name)
        self.assertEqual(self.test_heartbeat, json.loads(body))

    def test_load_state_successful_if_cl_node_exists_in_redis_and_redis_online(
            self) -> None:
        # We will test this for when transformed data has been already stored in
        # redis and for when default values have been stored in redis.

        # Test for when transformed data is stored in redis
        # Clean test db
        self.redis.delete_all()

        # Save state to Redis first
        save_chainlink_node_to_redis(self.redis, self.loaded_cl_node_trans_data)

        # Reset chainlink node to default values to detect the loading
        self.test_chainlink_node.reset()

        # Load state
        loaded_cl_node = self.test_data_transformer.load_state(
            self.test_chainlink_node)
        self.assertEqual(self.loaded_cl_node_trans_data, loaded_cl_node)

        # Now for when default values are stored in redis. At this point
        # self.test_chainlink_node will contain the original data due to the
        # loaded metrics.
        self.redis.delete_all()

        # Store default data
        save_chainlink_node_to_redis(self.redis,
                                     self.loaded_cl_node_default_data)

        loaded_cl_node = self.test_data_transformer.load_state(
            self.test_chainlink_node)
        self.assertEqual(self.loaded_cl_node_default_data, loaded_cl_node)

        # Clean test db
        self.redis.delete_all()

    def test_load_state_keeps_same_state_if_cl_node_in_redis_and_redis_offline(
            self) -> None:
        # In this test we will check for when redis has transformed data and
        # default data is stored in the state, and vice-versa.

        # Set the _do_not_use_if_recently_went_down function to return True
        # as if redis is down
        self.test_data_transformer.redis._do_not_use_if_recently_went_down = \
            lambda: True

        # First test for when redis has default values, and the state has
        # transformed metrics
        # Clean test db
        self.redis.delete_all()

        # Save state to Redis first.
        save_chainlink_node_to_redis(self.redis,
                                     self.loaded_cl_node_default_data)

        # Load state
        loaded_cl_node = self.test_data_transformer.load_state(
            self.test_chainlink_node)
        self.assertEqual(self.loaded_cl_node_trans_data, loaded_cl_node)

        # Now test for when redis has transformed data values, and the state is
        # default
        # Clean test db
        self.redis.delete_all()

        # Save state to Redis first
        save_chainlink_node_to_redis(self.redis, self.loaded_cl_node_trans_data)

        # Reset cl_node to default values
        self.test_chainlink_node.reset()

        # Load state
        loaded_cl_node = self.test_data_transformer.load_state(
            self.test_chainlink_node)
        self.assertEqual(self.loaded_cl_node_default_data, loaded_cl_node)

        # Clean test db
        self.redis.delete_all()

    def test_load_state_keeps_same_state_if_node_not_in_redis_and_redis_online(
            self) -> None:
        # We will perform this test for both when the current state has default
        # entries, and for when it has transformed data

        # Test for when the state contains transformed data
        # Clean test db
        self.redis.delete_all()

        # Load state
        loaded_cl_node = self.test_data_transformer.load_state(
            self.test_chainlink_node)
        self.assertEqual(self.loaded_cl_node_trans_data, loaded_cl_node)

        # Test for when the state contains default data
        # Clean test db
        self.redis.delete_all()
        self.test_chainlink_node.reset()

        # Load state
        loaded_cl_node = self.test_data_transformer.load_state(
            self.test_chainlink_node)
        self.assertEqual(self.loaded_cl_node_default_data, loaded_cl_node)

        # Clean test db
        self.redis.delete_all()

    def test_load_state_keeps_same_state_if_cl_node_not_in_redis_and_redis_off(
            self) -> None:
        # We will perform this test for both when the current state has default
        # entries, and for when it has transformed data

        # Set the _do_not_use_if_recently_went_down function to return True
        # as if redis is down
        self.test_data_transformer.redis._do_not_use_if_recently_went_down = \
            lambda: True

        # Test for when the state contains transformed data
        # Clean test db
        self.redis.delete_all()

        # Load state
        loaded_cl_node = self.test_data_transformer.load_state(
            self.test_chainlink_node)
        self.assertEqual(self.loaded_cl_node_trans_data, loaded_cl_node)

        # Test for when the state contains default data
        # Clean test db
        self.redis.delete_all()
        self.test_chainlink_node.reset()

        # Load state
        loaded_cl_node = self.test_data_transformer.load_state(
            self.test_chainlink_node)
        self.assertEqual(self.loaded_cl_node_default_data, loaded_cl_node)

        # Clean test db
        self.redis.delete_all()

    #
    # def test_update_state_raises_unexpected_data_exception_if_no_result_or_err(
    #         self) -> None:
    #     self.assertRaises(ReceivedUnexpectedDataException,
    #                       self.test_data_transformer._update_state,
    #                       self.invalid_transformed_data)
    #
    # def test_update_state_leaves_same_state_if_no_result_or_err_in_trans_data(
    #         self) -> None:
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     expected_state = copy.deepcopy(self.test_state)
    #
    #     # First confirm that an exception is still raised
    #     self.assertRaises(ReceivedUnexpectedDataException,
    #                       self.test_data_transformer._update_state,
    #                       self.invalid_transformed_data)
    #
    #     # Check that there are the same keys in the state
    #     self.assertEqual(expected_state.keys(),
    #                      self.test_data_transformer.state.keys())
    #
    #     # Check that the stored system state has the same variable values. This
    #     # must be done separately as otherwise the object's low level address
    #     # will be compared
    #     for system_id in expected_state.keys():
    #         self.assertDictEqual(
    #             expected_state[system_id].__dict__,
    #             self.test_data_transformer.state[system_id].__dict__)
    #
    # @parameterized.expand([
    #     ('result', 'self.transformed_data_example_result'),
    #     ('error', 'self.transformed_data_example_downtime_error'),
    # ])
    # def test_update_state_raises_key_error_exception_if_keys_do_not_exist(
    #         self, transformed_data_index: str, transformed_data: str) -> None:
    #     invalid_transformed_data = copy.deepcopy(eval(transformed_data))
    #
    #     del invalid_transformed_data[transformed_data_index]['data']
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #
    #     # First confirm that an exception is still raised
    #     self.assertRaises(KeyError, self.test_data_transformer._update_state,
    #                       invalid_transformed_data)
    #
    # @parameterized.expand([
    #     ('self.transformed_data_example_result', 'self.test_system_new_metrics',
    #      True),
    #     ('self.transformed_data_example_general_error', 'self.test_system',
    #      True),
    #     ('self.transformed_data_example_downtime_error',
    #      'self.test_system_down', False),
    # ])
    # def test_update_state_updates_state_correctly_on_result_data(
    #         self, transformed_data: str, expected_state: str,
    #         system_expected_up: bool) -> None:
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     self.test_data_transformer._state['dummy_id'] = self.test_data_str
    #     old_state = copy.deepcopy(self.test_data_transformer._state)
    #
    #     self.test_data_transformer._update_state(eval(transformed_data))
    #
    #     # Check that there are the same keys in the state
    #     self.assertEqual(old_state.keys(),
    #                      self.test_data_transformer.state.keys())
    #
    #     # Check that the systems not in question are not modified
    #     self.assertEqual(self.test_data_str,
    #                      self.test_data_transformer._state['dummy_id'])
    #
    #     # Check that the system's state values have been modified correctly
    #     self.assertDictEqual(
    #         eval(expected_state).__dict__,
    #         self.test_data_transformer._state[self.test_system_id].__dict__)
    #
    #     # Check that the system is marked as up/down accordingly
    #     if system_expected_up:
    #         self.assertFalse(
    #             self.test_data_transformer._state[self.test_system_id].is_down)
    #     else:
    #         self.assertTrue(
    #             self.test_data_transformer._state[self.test_system_id].is_down)
    #
    # @parameterized.expand([
    #     ('self.transformed_data_example_result',
    #      'self.transformed_data_example_result'),
    #     ('self.transformed_data_example_general_error',
    #      'self.transformed_data_example_general_error'),
    # ])
    # def test_process_transformed_data_for_saving_returns_expected_data(
    #         self, transformed_data: str, expected_processed_data: str) -> None:
    #     processed_data = \
    #         self.test_data_transformer._process_transformed_data_for_saving(
    #             eval(transformed_data))
    #     self.assertDictEqual(eval(expected_processed_data), processed_data)
    #
    # def test_proc_trans_data_for_saving_raises_unexp_data_except_on_unexp_data(
    #         self) -> None:
    #     self.assertRaises(
    #         ReceivedUnexpectedDataException,
    #         self.test_data_transformer._process_transformed_data_for_saving,
    #         self.invalid_transformed_data)
    #
    # @parameterized.expand([
    #     ('self.transformed_data_example_result',
    #      'self.test_data_for_alerting_result'),
    #     ('self.transformed_data_example_general_error',
    #      'self.transformed_data_example_general_error'),
    #     ('self.transformed_data_example_downtime_error',
    #      'self.test_data_for_alerting_down_error'),
    # ])
    # def test_process_transformed_data_for_alerting_returns_expected_data(
    #         self, transformed_data: str, expected_processed_data: str) -> None:
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     actual_data = \
    #         self.test_data_transformer._process_transformed_data_for_alerting(
    #             eval(transformed_data))
    #     self.assertDictEqual(eval(expected_processed_data), actual_data)
    #
    # def test_proc_trans_data_for_alerting_raise_unex_data_except_on_unex_data(
    #         self) -> None:
    #     self.assertRaises(
    #         ReceivedUnexpectedDataException,
    #         self.test_data_transformer._process_transformed_data_for_alerting,
    #         self.invalid_transformed_data)
    #
    # @mock.patch.object(SystemDataTransformer,
    #                    "_process_transformed_data_for_alerting")
    # @mock.patch.object(SystemDataTransformer,
    #                    "_process_transformed_data_for_saving")
    # def test_transform_data_returns_expected_data_if_result_and_first_mon_round(
    #         self, mock_process_for_saving, mock_process_for_alerting) -> None:
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     self.test_data_transformer._state[self.test_system_id].reset()
    #     mock_process_for_saving.return_value = {'key_1': 'val1'}
    #     mock_process_for_alerting.return_value = {'key_2': 'val2'}
    #
    #     trans_data, data_for_alerting, data_for_saving = \
    #         self.test_data_transformer._transform_data(
    #             self.raw_data_example_result)
    #
    #     # Set metrics which need more than 1 monitoring round to be computed
    #     # to None.
    #     expected_trans_data = copy.deepcopy(
    #         self.transformed_data_example_result)
    #     expected_trans_data['result']['data'][
    #         'network_transmit_bytes_per_second'] = None
    #     expected_trans_data['result']['data'][
    #         'network_receive_bytes_per_second'] = None
    #     expected_trans_data['result']['data'][
    #         'disk_io_time_seconds_in_interval'] = None
    #
    #     self.assertDictEqual(expected_trans_data, trans_data)
    #     self.assertDictEqual({'key_2': 'val2'}, data_for_alerting)
    #     self.assertDictEqual({'key_1': 'val1'}, data_for_saving)
    #
    # @mock.patch.object(SystemDataTransformer,
    #                    "_process_transformed_data_for_alerting")
    # @mock.patch.object(SystemDataTransformer,
    #                    "_process_transformed_data_for_saving")
    # def test_transform_data_ret_expected_data_if_result_and_second_mon_round(
    #         self, mock_process_for_saving, mock_process_for_alerting) -> None:
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     mock_process_for_saving.return_value = {'key_1': 'val1'}
    #     mock_process_for_alerting.return_value = {'key_2': 'val2'}
    #
    #     trans_data, data_for_alerting, data_for_saving = \
    #         self.test_data_transformer._transform_data(
    #             self.raw_data_example_result)
    #
    #     self.assertDictEqual(self.transformed_data_example_result, trans_data)
    #     self.assertDictEqual({'key_2': 'val2'}, data_for_alerting)
    #     self.assertDictEqual({'key_1': 'val1'}, data_for_saving)
    #
    # @parameterized.expand([
    #     ('self.raw_data_example_general_error',
    #      'self.transformed_data_example_general_error'),
    #     ('self.raw_data_example_downtime_error',
    #      'self.transformed_data_example_downtime_error'),
    # ])
    # @mock.patch.object(SystemDataTransformer,
    #                    "_process_transformed_data_for_alerting")
    # @mock.patch.object(SystemDataTransformer,
    #                    "_process_transformed_data_for_saving")
    # def test_transform_data_returns_expected_data_if_error(
    #         self, raw_data: str, expected_processed_data: str,
    #         mock_process_for_saving, mock_process_for_alerting) -> None:
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     mock_process_for_saving.return_value = {'key_1': 'val1'}
    #     mock_process_for_alerting.return_value = {'key_2': 'val2'}
    #
    #     trans_data, data_for_alerting, data_for_saving = \
    #         self.test_data_transformer._transform_data(eval(raw_data))
    #
    #     self.assertDictEqual(eval(expected_processed_data), trans_data)
    #     self.assertDictEqual({'key_2': 'val2'}, data_for_alerting)
    #     self.assertDictEqual({'key_1': 'val1'}, data_for_saving)
    #
    # def test_transform_data_raises_unexpected_data_exception_on_unexpected_data(
    #         self) -> None:
    #     self.assertRaises(ReceivedUnexpectedDataException,
    #                       self.test_data_transformer._transform_data,
    #                       self.invalid_transformed_data)
    #
    # def test_transform_data_raises_key_error_if_key_does_not_exist_result(
    #         self) -> None:
    #     # Test for non first monitoring round data
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     raw_data = copy.deepcopy(self.raw_data_example_result)
    #     del raw_data['result']['meta_data']['time']
    #     self.assertRaises(KeyError, self.test_data_transformer._transform_data,
    #                       raw_data)
    #
    #     # Test for first monitoring round data
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     self.test_system.reset()
    #     raw_data = copy.deepcopy(self.raw_data_example_result)
    #     del raw_data['result']['meta_data']['time']
    #     self.assertRaises(KeyError, self.test_data_transformer._transform_data,
    #                       raw_data)
    #
    # def test_transform_data_raises_key_error_if_key_does_not_exist_error(
    #         self) -> None:
    #     # Test when the error is not related to downtime
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     raw_data = copy.deepcopy(self.raw_data_example_general_error)
    #     del raw_data['error']['meta_data']
    #     self.assertRaises(KeyError, self.test_data_transformer._transform_data,
    #                       raw_data)
    #
    #     # Test when the error is related to downtime
    #     raw_data = copy.deepcopy(self.raw_data_example_downtime_error)
    #     del raw_data['error']['meta_data']
    #     self.assertRaises(KeyError, self.test_data_transformer._transform_data,
    #                       raw_data)
    #
    # @parameterized.expand([
    #     ('self.transformed_data_example_result',
    #      'self.test_data_for_alerting_result',
    #      'self.transformed_data_example_result'),
    #     ('self.transformed_data_example_general_error',
    #      'self.transformed_data_example_general_error',
    #      'self.transformed_data_example_general_error'),
    # ])
    # def test_place_latest_data_on_queue_places_the_correct_data_on_queue(
    #         self, transformed_data: str, data_for_alerting: str,
    #         data_for_saving: str) -> None:
    #     self.test_data_transformer._place_latest_data_on_queue(
    #         eval(transformed_data), eval(data_for_alerting),
    #         eval(data_for_saving)
    #     )
    #     expected_data_for_alerting = {
    #         'exchange': ALERT_EXCHANGE,
    #         'routing_key': SYSTEM_TRANSFORMED_DATA_ROUTING_KEY_TEMPLATE.format(
    #             self.test_system_parent_id),
    #         'data': eval(data_for_alerting),
    #         'properties': pika.BasicProperties(delivery_mode=2),
    #         'mandatory': True
    #     }
    #     expected_data_for_saving = {
    #         'exchange': STORE_EXCHANGE,
    #         'routing_key': SYSTEM_TRANSFORMED_DATA_ROUTING_KEY_TEMPLATE.format(
    #             self.test_system_parent_id),
    #         'data': eval(data_for_saving),
    #         'properties': pika.BasicProperties(delivery_mode=2),
    #         'mandatory': True
    #     }
    #
    #     self.assertEqual(2, self.test_data_transformer.publishing_queue.qsize())
    #     self.assertDictEqual(
    #         expected_data_for_alerting,
    #         self.test_data_transformer.publishing_queue.queue[0])
    #     self.assertDictEqual(
    #         expected_data_for_saving,
    #         self.test_data_transformer.publishing_queue.queue[1])
    #
    # @parameterized.expand([
    #     ('result', 'self.transformed_data_example_result',),
    #     ('error', 'self.transformed_data_example_general_error',),
    # ])
    # def test_place_latest_data_on_queue_raises_key_error_if_keys_missing(
    #         self, response_index_key, transformed_data) -> None:
    #     invalid_transformed_data = copy.deepcopy(eval(transformed_data))
    #     del invalid_transformed_data[response_index_key]['meta_data']
    #     self.assertRaises(
    #         KeyError, self.test_data_transformer._place_latest_data_on_queue,
    #         invalid_transformed_data, {}, {})
    #
    # @parameterized.expand([({}, False,), ('self.test_state', True), ])
    # @mock.patch.object(SystemDataTransformer, "_transform_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_transforms_data_if_data_valid(
    #         self, state: Union[bool, str], state_is_str: bool, mock_ack,
    #         mock_trans_data) -> None:
    #     # We will check that the data is transformed by checking that
    #     # `_transform_data` is called correctly. The actual transformations are
    #     # already tested. Note we will test for both result and error, and when
    #     # the system is both in the state and not in the state.
    #     mock_ack.return_value = None
    #     mock_trans_data.return_value = (None, None, None)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_general_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         if state_is_str:
    #             self.test_data_transformer._state = copy.deepcopy(eval(state))
    #         else:
    #             self.test_data_transformer._state = copy.deepcopy(state)
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         mock_trans_data.assert_called_once_with(
    #             self.raw_data_example_result)
    #
    #         # To reset the state as if the system was not already added
    #         if state_is_str:
    #             self.test_data_transformer._state = copy.deepcopy(eval(state))
    #         else:
    #             self.test_data_transformer._state = copy.deepcopy(state)
    #
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #
    #         self.assertEqual(2, mock_trans_data.call_count)
    #         args, _ = mock_trans_data.call_args
    #         self.assertEqual(self.raw_data_example_general_error, args[0])
    #         self.assertEqual(1, len(args))
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @parameterized.expand([
    #     ({},), (None,), ("test",), ({'bad_key': 'bad_value'},)
    # ])
    # @mock.patch.object(SystemDataTransformer, "_transform_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_does_not_call_trans_data_if_err_res_not_in_data(
    #         self, invalid_data: Dict, mock_ack, mock_trans_data) -> None:
    #     mock_ack.return_value = None
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body = json.dumps(invalid_data)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body)
    #
    #         mock_trans_data.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     mock_ack.assert_called_once()
    #
    # @mock.patch.object(SystemDataTransformer, "_transform_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_does_not_call_trans_data_if_missing_keys_in_data(
    #         self, mock_ack, mock_trans_data) -> None:
    #     mock_ack.return_value = None
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`. Here we must cater for both the error
    #         # and result cases.
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps({'result': self.invalid_transformed_data})
    #         body_error = json.dumps({'error': self.invalid_transformed_data})
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #
    #         mock_trans_data.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_updates_state_if_no_processing_errors_new_system(
    #         self, mock_ack) -> None:
    #     # To make sure there is no state in redis as the state must be compared.
    #     # We will check that the state has been updated correctly.
    #     self.redis.delete_all()
    #
    #     mock_ack.return_value = None
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_general_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Make the state non-empty to check that the update does not modify
    #         # systems not in question
    #         self.test_data_transformer._state['system2'] = self.test_data_str
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #
    #         # Check that there are 2 entries in the state, one which was not
    #         # modified, and the other having metrics the same as the newly
    #         # given data.
    #         expected_data = copy.deepcopy(self.test_system_new_metrics)
    #         expected_data.set_network_transmit_bytes_per_second(None)
    #         expected_data.set_network_receive_bytes_per_second(None)
    #         expected_data.set_disk_io_time_seconds_in_interval(None)
    #         self.assertEqual(2, len(self.test_data_transformer._state.keys()))
    #         self.assertEqual(self.test_data_str,
    #                          self.test_data_transformer._state['system2'])
    #         self.assertEqual(
    #             expected_data.__dict__,
    #             self.test_data_transformer._state[self.test_system_id].__dict__)
    #
    #         # To reset the state as if the system was not already added
    #         del self.test_data_transformer._state[self.test_system_id]
    #         self.redis.delete_all()
    #
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #
    #         # Check that there are 2 entries in the state, one which was not
    #         # modified, and the other having metrics the same as the newly
    #         # given data.
    #         self.assertEqual(2, len(self.test_data_transformer._state.keys()))
    #         self.assertEqual(self.test_data_str,
    #                          self.test_data_transformer._state['system2'])
    #         expected_data = System(self.test_system_name, self.test_system_id,
    #                                self.test_system_parent_id)
    #         self.assertEqual(
    #             expected_data.__dict__,
    #             self.test_data_transformer._state[self.test_system_id].__dict__)
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_updates_state_if_no_process_errors_sys_in_state(
    #         self, mock_ack) -> None:
    #     # We will check that the state has been updated correctly.
    #     mock_ack.return_value = None
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_general_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Define a state. Make sure the state in question is stored in
    #         # redis.
    #         self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #         save_system_to_redis(self.redis, self.test_system)
    #         self.test_data_transformer._state['system2'] = self.test_data_str
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #
    #         # Check that there are 2 entries in the state, one which was not
    #         # modified, and the other having metrics the same as the newly
    #         # given data.
    #         self.assertEqual(2, len(self.test_data_transformer._state.keys()))
    #         self.assertEqual(self.test_data_str,
    #                          self.test_data_transformer._state['system2'])
    #         self.assertEqual(
    #             self.test_system_new_metrics.__dict__,
    #             self.test_data_transformer._state[self.test_system_id].__dict__)
    #
    #         # Reset state for error path
    #         self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #         save_system_to_redis(self.redis, self.test_system)
    #         self.test_data_transformer._state['system2'] = self.test_data_str
    #
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #
    #         # Check that there are 2 entries in the state, one which was not
    #         # modified, and the other having metrics the same as the newly
    #         # given data.
    #         self.assertEqual(2, len(self.test_data_transformer._state.keys()))
    #         self.assertEqual(self.test_data_str,
    #                          self.test_data_transformer._state['system2'])
    #         self.assertEqual(
    #             self.test_system.__dict__,
    #             self.test_data_transformer._state[self.test_system_id].__dict__)
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @parameterized.expand([
    #     ({},), (None,), ("test",), ({'bad_key': 'bad_value'},)
    # ])
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_does_not_update_state_if_res_or_err_not_in_data(
    #         self, invalid_data: Dict, mock_ack) -> None:
    #     mock_ack.return_value = None
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body = json.dumps(invalid_data)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Make the state non-empty and save it to redis
    #         self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #         save_system_to_redis(self.redis, self.test_system)
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body)
    #
    #         # Check that there is 1 entry in the state, one which was not
    #         # modified.
    #         expected_data = copy.deepcopy(self.test_system)
    #         self.assertEqual(1, len(self.test_data_transformer._state.keys()))
    #         self.assertEqual(
    #             expected_data.__dict__,
    #             self.test_data_transformer._state[self.test_system_id].__dict__)
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     mock_ack.assert_called_once()
    #
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_does_not_update_state_if_missing_keys_in_data(
    #         self, mock_ack) -> None:
    #     mock_ack.return_value = None
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         data_result = copy.deepcopy(self.raw_data_example_result)
    #         del data_result['result']['meta_data']
    #         data_error = copy.deepcopy(self.raw_data_example_downtime_error)
    #         del data_error['error']['meta_data']
    #         body_result = json.dumps(data_result)
    #         body_error = json.dumps(data_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Make the state non-empty and save it to redis
    #         self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #         save_system_to_redis(self.redis, self.test_system)
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #
    #         # Check that there is 1 entry in the state, one which was not
    #         # modified.
    #         expected_data = copy.deepcopy(self.test_system)
    #         self.assertEqual(1, len(self.test_data_transformer._state.keys()))
    #         self.assertEqual(
    #             expected_data.__dict__,
    #             self.test_data_transformer._state[self.test_system_id].__dict__)
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_transform_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_does_not_update_state_if_transform_data_exception(
    #         self, mock_ack, mock_transform_data) -> None:
    #     mock_ack.return_value = None
    #     mock_transform_data.side_effect = self.test_exception
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Make the state non-empty and save it to redis
    #         self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #         save_system_to_redis(self.redis, self.test_system)
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #
    #         # Check that there is 1 entry in the state, one which was not
    #         # modified.
    #         expected_data = copy.deepcopy(self.test_system)
    #         self.assertEqual(1, len(self.test_data_transformer._state.keys()))
    #         self.assertEqual(
    #             expected_data.__dict__,
    #             self.test_data_transformer._state[self.test_system_id].__dict__)
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_transform_data")
    # @mock.patch.object(SystemDataTransformer, "_place_latest_data_on_queue")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_places_data_on_queue_if_no_processing_errors(
    #         self, mock_ack, mock_place_on_queue, mock_trans_data) -> None:
    #     mock_ack.return_value = None
    #     mock_trans_data.side_effect = [
    #         (
    #             self.transformed_data_example_result,
    #             self.test_data_for_alerting_result,
    #             self.transformed_data_example_result
    #         ),
    #         (
    #             self.transformed_data_example_downtime_error,
    #             self.test_data_for_alerting_down_error,
    #             self.transformed_data_example_downtime_error
    #         ),
    #     ]
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_general_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         args, _ = mock_place_on_queue.call_args
    #         self.assertDictEqual(self.transformed_data_example_result, args[0])
    #         self.assertDictEqual(self.test_data_for_alerting_result, args[1])
    #         self.assertDictEqual(self.transformed_data_example_result, args[2])
    #         self.assertEqual(3, len(args))
    #
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         args, _ = mock_place_on_queue.call_args
    #         self.assertDictEqual(self.transformed_data_example_downtime_error,
    #                              args[0])
    #         self.assertDictEqual(self.test_data_for_alerting_down_error,
    #                              args[1])
    #         self.assertDictEqual(self.transformed_data_example_downtime_error,
    #                              args[2])
    #         self.assertEqual(3, len(args))
    #
    #         self.assertEqual(2, mock_place_on_queue.call_count)
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @parameterized.expand([
    #     ({},), (None,), ("test",), ({'bad_key': 'bad_value'},)
    # ])
    # @mock.patch.object(SystemDataTransformer, "_place_latest_data_on_queue")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_no_data_on_queue_if_result_or_error_not_in_data(
    #         self, invalid_data: Dict, mock_ack, mock_place_on_queue) -> None:
    #     mock_ack.return_value = None
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body = json.dumps(invalid_data)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body)
    #         # Check that place_on_queue was not called
    #         mock_place_on_queue.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     mock_ack.assert_called_once()
    #
    # @mock.patch.object(SystemDataTransformer, "_place_latest_data_on_queue")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_no_data_on_queue_if_missing_keys_in_data(
    #         self, mock_ack, mock_place_on_queue) -> None:
    #     mock_ack.return_value = None
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         data_result = copy.deepcopy(self.raw_data_example_result)
    #         del data_result['result']['meta_data']
    #         data_error = copy.deepcopy(self.raw_data_example_downtime_error)
    #         del data_error['error']['meta_data']
    #         body_result = json.dumps(data_result)
    #         body_error = json.dumps(data_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that place_on_queue was not called
    #         mock_place_on_queue.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_transform_data")
    # @mock.patch.object(SystemDataTransformer, "_place_latest_data_on_queue")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_no_data_on_queue_if_transform_data_exception(
    #         self, mock_ack, mock_place_on_queue, mock_transform_data) -> None:
    #     mock_ack.return_value = None
    #     mock_transform_data.side_effect = self.test_exception
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_general_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that place_on_queue was not called
    #         mock_place_on_queue.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_update_state")
    # @mock.patch.object(SystemDataTransformer, "_place_latest_data_on_queue")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_no_data_on_queue_if_update_state_exception(
    #         self, mock_ack, mock_place_on_queue, mock_update_state) -> None:
    #     mock_ack.return_value = None
    #     mock_update_state.side_effect = self.test_exception
    #
    #     # Load the state to avoid errors when having the system already in
    #     # redis due to other tests.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_general_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that place_on_queue was not called
    #         mock_place_on_queue.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_sends_data_waiting_on_queue_if_no_process_errors(
    #         self, mock_ack, mock_send_data) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.return_value = None
    #
    #     # Load the state to avoid errors when having the system already in
    #     # redis due to other tests.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_general_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that send_data was called
    #         self.assertEqual(2, mock_send_data.call_count)
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_transform_data")
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_sends_data_waiting_on_queue_if_process_errors(
    #         self, mock_ack, mock_send_data, mock_transform_data) -> None:
    #     # We will test this by mocking that _transform_data returns an
    #     # exception. It is safe to assume that the other error paths will result
    #     # in the same outcome as all the errors are caught. Thus this test-case
    #     # was essentially done for completion.
    #     mock_ack.return_value = None
    #     mock_send_data.return_value = None
    #     mock_transform_data.side_effect = self.test_exception
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that send_data was called
    #         self.assertEqual(2, mock_send_data.call_count)
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @freeze_time("2012-01-01")
    # @mock.patch.object(SystemDataTransformer, "_send_heartbeat")
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_sends_hb_if_no_proc_errors_and_send_data_success(
    #         self, mock_ack, mock_send_data, mock_send_hb) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.return_value = None
    #     mock_send_hb.return_value = None
    #     test_hb = {
    #         'component_name': self.transformer_name,
    #         'is_alive': True,
    #         'timestamp': datetime.now().timestamp()
    #     }
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         mock_send_hb.assert_called_once_with(test_hb)
    #
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that send_heartbeat was called
    #         self.assertEqual(2, mock_send_hb.call_count)
    #         args, _ = mock_send_hb.call_args
    #         self.assertDictEqual(test_hb, args[0])
    #         self.assertEqual(1, len(args))
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_transform_data")
    # @mock.patch.object(SystemDataTransformer, "_send_heartbeat")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_does_not_send_hb_if_processing_errors_trans_data(
    #         self, mock_ack, mock_send_hb, mock_trans_data) -> None:
    #     mock_ack.return_value = None
    #     mock_send_hb.return_value = None
    #     mock_trans_data.side_effect = self.test_exception
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that send_heartbeat was not called
    #         mock_send_hb.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_update_state")
    # @mock.patch.object(SystemDataTransformer, "_send_heartbeat")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_does_not_send_hb_if_proc_errors_update_state(
    #         self, mock_ack, mock_send_hb, mock_update_state) -> None:
    #     mock_ack.return_value = None
    #     mock_send_hb.return_value = None
    #     mock_update_state.side_effect = self.test_exception
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that send_heartbeat was not called
    #         mock_send_hb.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(SystemDataTransformer, "_send_heartbeat")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_does_not_send_hb_if_send_data_fails(
    #         self, mock_ack, mock_send_hb, mock_send_data) -> None:
    #     mock_ack.return_value = None
    #     mock_send_hb.return_value = None
    #     mock_send_data.side_effect = MessageWasNotDeliveredException('test err')
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_result)
    #         self.test_data_transformer._process_raw_data(blocking_channel,
    #                                                      method, properties,
    #                                                      body_error)
    #         # Check that send_heartbeat was not called
    #         mock_send_hb.assert_not_called()
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_raises_amqp_conn_err_if_conn_err_in_send_data(
    #         self, mock_ack, mock_send_data) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.side_effect = pika.exceptions.AMQPConnectionError(
    #         'test err')
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data and assert exception
    #         self.assertRaises(pika.exceptions.AMQPConnectionError,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_result
    #                           )
    #         self.assertRaises(pika.exceptions.AMQPConnectionError,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_error
    #                           )
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_heartbeat")
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_raises_amqp_conn_err_if_conn_err_in_send_hb(
    #         self, mock_ack, mock_send_data, mock_send_hb) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.return_value = None
    #     mock_send_hb.side_effect = pika.exceptions.AMQPConnectionError(
    #         'test err')
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data and assert exception
    #         self.assertRaises(pika.exceptions.AMQPConnectionError,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_result
    #                           )
    #         self.assertRaises(pika.exceptions.AMQPConnectionError,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_error
    #                           )
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_raises_amqp_chan_err_if_chan_err_in_send_data(
    #         self, mock_ack, mock_send_data) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.side_effect = pika.exceptions.AMQPChannelError(
    #         'test err')
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data and assert exception
    #         self.assertRaises(pika.exceptions.AMQPChannelError,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_result
    #                           )
    #         self.assertRaises(pika.exceptions.AMQPChannelError,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_error
    #                           )
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_heartbeat")
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_raises_amqp_chan_err_if_chan_err_in_send_hb(
    #         self, mock_ack, mock_send_data, mock_send_hb) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.return_value = None
    #     mock_send_hb.side_effect = pika.exceptions.AMQPChannelError(
    #         'test err')
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data and assert exception
    #         self.assertRaises(pika.exceptions.AMQPChannelError,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_result
    #                           )
    #         self.assertRaises(pika.exceptions.AMQPChannelError,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_error
    #                           )
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_unexpec_except_if_unexpec_except_in_send_data(
    #         self, mock_ack, mock_send_data) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.side_effect = self.test_exception
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data and assert exception
    #         self.assertRaises(PANICException,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_result
    #                           )
    #         self.assertRaises(PANICException,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_error
    #                           )
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_heartbeat")
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_unexpec_except_if_unexpec_except_in_send_hb(
    #         self, mock_ack, mock_send_data, mock_send_hb) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.return_value = None
    #     mock_send_hb.side_effect = self.test_exception
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data and assert exception
    #         self.assertRaises(PANICException,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_result
    #                           )
    #         self.assertRaises(PANICException,
    #                           self.test_data_transformer._process_raw_data,
    #                           blocking_channel, method, properties, body_error
    #                           )
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_no_msg_not_del_exception_if_raised_by_send_data(
    #         self, mock_ack, mock_send_data) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.side_effect = MessageWasNotDeliveredException('test err')
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data. Test would fail if an exception is raised
    #         self.test_data_transformer._process_raw_data(
    #             blocking_channel, method, properties, body_result
    #         )
    #         self.test_data_transformer._process_raw_data(
    #             blocking_channel, method, properties, body_error
    #         )
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
    #
    # @mock.patch.object(SystemDataTransformer, "_send_heartbeat")
    # @mock.patch.object(SystemDataTransformer, "_send_data")
    # @mock.patch.object(RabbitMQApi, "basic_ack")
    # def test_process_raw_data_no_msg_not_del_exception_if_raised_by_send_hb(
    #         self, mock_ack, mock_send_data, mock_send_hb) -> None:
    #     mock_ack.return_value = None
    #     mock_send_data.return_value = None
    #     mock_send_hb.side_effect = MessageWasNotDeliveredException('test err')
    #
    #     # Load the state to avoid having the system already in redis, hence
    #     # avoiding errors.
    #     self.test_data_transformer._state = copy.deepcopy(self.test_state)
    #     try:
    #         # We must initialise rabbit to the environment and parameters needed
    #         # by `_process_raw_data`
    #         self.test_data_transformer._initialise_rabbitmq()
    #         blocking_channel = self.test_data_transformer.rabbitmq.channel
    #         method = pika.spec.Basic.Deliver(
    #             routing_key=SYSTEM_RAW_DATA_ROUTING_KEY)
    #         body_result = json.dumps(self.raw_data_example_result)
    #         body_error = json.dumps(self.raw_data_example_downtime_error)
    #         properties = pika.spec.BasicProperties()
    #
    #         # Send raw data. Test would fail if an exception is raised
    #         self.test_data_transformer._process_raw_data(
    #             blocking_channel, method, properties, body_result
    #         )
    #         self.test_data_transformer._process_raw_data(
    #             blocking_channel, method, properties, body_error
    #         )
    #     except Exception as e:
    #         self.fail("Test failed: {}".format(e))
    #
    #     # Make sure that the message has been acknowledged. This must be done
    #     # in all test cases to cover every possible case, and avoid doing a
    #     # very large amount of tests around this.
    #     self.assertEqual(2, mock_ack.call_count)
