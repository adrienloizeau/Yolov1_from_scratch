import sys
import torch 
import torchvision.transforms as transforms
import torch.optim as optim
import torchvision.transforms.functional as FT
from tqdm import tqdm
from torch.utils.data import DataLoader
import argparse
from model import Yolov1
from dataset import VOCDataset
from utils import (
    intersection_over_union, 
    non_max_suppression, 
    mean_average_precision,
    cellboxes_to_boxes,
    get_bboxes,
    plot_image, 
    save_checkpoint, 
    load_checkpoint
)
from loss import YoloLoss



parser = argparse.ArgumentParser()
parser.add_argument('--dir', type=str, default='data/images', help='path to the directory all the files')
args = parser.parse_args()

seed = 123
torch.manual_seed(seed)


# Hyperparameters 
LEARNING_RATE = 2e-5
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
BATCH_SIZE = 16
WEIGHT_DECAY = 0 # Question :No regularization to get faster training ? 
EPOCHS = 100
NUM_WORKERS = 2
PIN_MEMORY = True
LOAD_MODEL  = False
LOAD_MODEL_FILE = "overfit.pth.tar"
IMG_DIR = args.dir + "/images"
LABEL_DIR =  args.dir + "/labels"

class Compose(object):
    def __init__(self, transforms) -> None:
        self.transforms = transforms
    def __call__(self, img, bboxes):
        for t in self.transforms:
            img, bboxes = t(img), bboxes
        return img, bboxes

transforms = Compose([transforms.Resize((448,448)), transforms.ToTensor()])

def train_fn(train_loader, model, optimizer, loss_fn):
    loop = tqdm(train_loader, leave = True)
    mean_loss = []

    for batch_idx, (x,y) in enumerate(loop):
        x, y= x.to(DEVICE), y.to(DEVICE)
        output = model(x)
        loss = loss_fn(output,y)
        mean_loss.append(loss.item())
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        # Update the progress bar
        loop.set_postfix(loss = loss.item())
    
    print(f"Mean loss was {sum(mean_loss)/len(mean_loss)}")


def main():
    torch.autograd.set_detect_anomaly(True)

    model = Yolov1().to(DEVICE)
    loss_fn = YoloLoss()
    epoch = EPOCHS 
    optimizer = optim.Adam(
        model.parameters(),
        lr = LEARNING_RATE, weight_decay  =WEIGHT_DECAY
    )
    if LOAD_MODEL:
        load_checkpoint(torch.load(LOAD_MODEL_FILE), model, optimizer)

    train_dataset = VOCDataset(
        args.dir + "/8examples.csv",
        transform = transforms,
        img_dir = IMG_DIR,
        label_dir= LABEL_DIR
    
    )
    test_dataset = VOCDataset(
        args.dir + "/test.csv",
        transform = transforms,
        img_dir = IMG_DIR,
        label_dir= LABEL_DIR
    )

    train_loader = DataLoader(
        dataset = train_dataset,
        batch_size = BATCH_SIZE,
        num_workers = NUM_WORKERS,
        pin_memory = PIN_MEMORY,
        shuffle = True,
        drop_last = False
    )
    test_loader = DataLoader(
        dataset = test_dataset,
        batch_size = BATCH_SIZE,
        num_workers = NUM_WORKERS,
        pin_memory = PIN_MEMORY,
        shuffle = True,
        drop_last = False
    )

    for epoch in range(EPOCHS):
        for x, y in train_loader:
           x = x.to(DEVICE)
        pred_boxes, target_boxes = get_bboxes(
            train_loader, model, iou_threshold = 0.5, threshold =0.4, device = DEVICE
        )
        mean_average_prec = mean_average_precision(
            pred_boxes, target_boxes, iou_threshold = 0.5, box_format = "midpoint"
        )
        print(f"Train mAP:{mean_average_prec}")
        if mean_average_prec > 0.9:
            checkpoint = {
                "state_dict": model.state_dict(),
                "optimizer": optimizer.state_dict(),
            }
            save_checkpoint(checkpoint, filename=LOAD_MODEL_FILE)
            import time
            time.sleep(10)
            for idx in range(8):
               bboxes = cellboxes_to_boxes(model(x))
               bboxes = non_max_suppression(bboxes[idx], iou_threshold=0.5, threshold=0.4, box_format="midpoint")
               plot_image(x[idx].permute(1,2,0).to("cpu"), bboxes)           
            sys.exit()

        train_fn(train_loader, model, optimizer, loss_fn)

if __name__ == "__main__":
    main()
