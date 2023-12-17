
# make sure you put the python in a new env

# python3 -m venv myenv

# source myenv/bin/activate


# apt-get update

# apt-get install unzip 
# apt-get install vim 

# wget https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
# unzip awscli-exe-linux-x86_64.zip
# ./aws/install

# aws configure

# Access Key:  AKIA2IUAQDAPNTNWRZVF
# 		Secret:  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
# location : ap-south-1
# format: text
# mkdir data
# aws configure set default.s3.max_concurrent_requests 50
# aws s3 cp s3://lambda1234akshit/data data  --recursive

# pip install TTS

# cd myenv/lib/python3.10/site-packages/trainer
# vim trainer.py

#make sure that you change the limit on the
# if platform.system() != "Windows":
#             # https://github.com/pytorch/pytorch/issues/973
#             import resource  # pylint: disable=import-outside-toplevel
#             current_soft, current_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
#             desired_soft_limit = 4096
#         # Set new soft limit to the lesser of the desired limit and the current hard limit
#             new_soft_limit = min(desired_soft_limit, current_hard)
#         # Ensure the new soft limit is not higher than the current soft limit
#             new_soft_limit = min(new_soft_limit, current_soft)
#            # resource.setrlimit(resource.RLIMIT_NOFILE, (new_soft_limit, current_hard))


#python distribute.py --script train.py --gpus "0,1"






# import boto3

# # Initialize a session using Boto3
# session = boto3.Session(
#     aws_access_key_id='AKIA2IUAQDAPNTNWRZVF',
#     aws_secret_access_key='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',
#     region_name='ap-south-1'
# )

# # Create an S3 client
# s3 = session.client('s3')

# # Specify the S3 bucket and folder
# bucket_name = 'lambda1234akshit'
# folder_path = 'data/wavs'

# # Local directory to save files
# local_directory = 'data/wavs/'

# # Get the list of files
# response = s3.list_objects_v2(Bucket=bucket_name, Prefix=folder_path)

# # Counter for files
# file_count = 0

# # Download the first 1000 files
# if 'Contents' in response:
#     for item in response['Contents']:
#         if file_count < 1000:
#             file_name = item['Key']
#             s3.download_file(bucket_name, file_name, local_directory + file_name.split('/')[-1])
#             file_count += 1
#         else:
#             break

# print(f"Downloaded {file_count} files to {local_directory}")






























import os
import argparse

from trainer import Trainer, TrainerArgs
from TTS.tts.configs.shared_configs import BaseDatasetConfig
from TTS.tts.configs.vits_config import VitsConfig
from TTS.tts.datasets import load_tts_samples
from TTS.tts.models.vits import Vits, VitsAudioConfig
from TTS.tts.utils.text.tokenizer import TTSTokenizer
from TTS.utils.audio import AudioProcessor

import sys
def main():
    output_path = os.path.dirname(os.path.abspath(__file__))

    # Initialize the dataset configuration
    dataset_config = BaseDatasetConfig(
        formatter="ljspeech",
        meta_file_train=os.path.join(output_path, "data/metadata.csv"),
        path=os.path.join(output_path, "data/wavs/")
    )

    # Parse the arguments

    parser = argparse.ArgumentParser(description='Training script')

    # Define your arguments here, matching those in your `distribute.py` script
    parser.add_argument("--continue_path", type=str, help="Path to continue training from")
    parser.add_argument("--restore_path", type=str, help="Path to restore training from")
    parser.add_argument("--group_id", type=str, help="Group ID for the training session")
    parser.add_argument("--use_ddp", type=str, help="Flag to use Distributed Data Parallel")
    parser.add_argument("--rank", type=int, help="Rank of the process in distributed training")

    # Add other arguments as needed for TrainerArgs and your training configuration
    # ...

    # Parse the arguments
    args = parser.parse_args()


    # Initialize the audio configuration
    audio_config = VitsAudioConfig(
        sample_rate=22050, win_length=1024, hop_length=256, num_mels=80, mel_fmin=0, mel_fmax=None
    )

    # Initialize the VITS configuration
    config = VitsConfig(
        audio=audio_config,
        run_name="vits_ljspeech",
        batch_size=32,
        eval_batch_size=16,
        batch_group_size=5,
        num_loader_workers=8,
        num_eval_loader_workers=4,
        run_eval=True,
        test_delay_epochs=-1,
        epochs=1000,
        text_cleaner="english_cleaners",
        use_phonemes=True,
        phoneme_language="en-us",
        phoneme_cache_path=os.path.join(output_path, "phoneme_cache"),
        compute_input_seq_cache=True,
        print_step=25,
        print_eval=True,
        mixed_precision=True,
        output_path=output_path,
        datasets=[dataset_config],
        cudnn_benchmark=False,
    )

    # Initialize the audio processor
    ap = AudioProcessor.init_from_config(config)

    # Initialize the tokenizer
    tokenizer, config = TTSTokenizer.init_from_config(config)

    # Load data samples
    train_samples, eval_samples = load_tts_samples(
        dataset_config,
        eval_split=True,
        eval_split_max_size=config.eval_split_max_size,
        eval_split_size=config.eval_split_size,
    )

    # Initialize the model
    model = Vits(config, ap, tokenizer, speaker_manager=None)


    ## ned to make sure that  the arguments that are being parsed here are following the structure of the dataclass.


    trainer_args = TrainerArgs()
    for key, value in vars(args).items():
        if value is not None:
            setattr(trainer_args, key, value)


    trainer = Trainer(
        trainer_args,
        config,
        output_path,
        model=model,
        train_samples=train_samples,
        eval_samples=eval_samples,
    )

    # Start training
    trainer.fit()

if __name__ == "__main__":
    main()  # Pass None to use sys.argv by default
