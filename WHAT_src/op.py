import numpy as np
from torch.utils.tensorboard import SummaryWriter

from model import *
from loss import Loss
from util import make_optimizer, calc_psnr


class Operator:
    def __init__(self, config, ckeck_point, device):
        self.device = device
        self.config = config
        self.uncertainty = config.uncertainty
        self.ckpt = ckeck_point
        self.tensorboard = config.tensorboard
        if self.tensorboard:
            self.summary_writer = SummaryWriter(self.ckpt.log_dir, 300)

        # set model, criterion, optimizer
        self.model = Model(config, device)
        self.criterion = Loss(config, device)
        self.optimizer = make_optimizer(config, self.model)

        # load ckpt, model, optimizer
        if config.is_resume or not config.is_train:
            print("Loading model... ")
            self.load(self.ckpt)
            print(self.ckpt.last_epoch, self.ckpt.global_step)

    def train(self, data_loader):
        last_epoch = self.ckpt.last_epoch
        train_batch_num = len(data_loader['train'])
        self.model.train()

        for epoch in range(last_epoch, self.config.epochs):
            for batch_idx, batch_data in enumerate(data_loader['train']):
                batch_input, batch_label = batch_data.to(self.config.device)

                # forward
                batch_results = self.model(batch_input)
                loss = self.criterion(batch_results, batch_input)

                # backward
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
                print('Epoch: {:03d}/{:03d}, Iter: {:03d}/{:03d}, Loss: {:5f}'
                      .format(epoch, self.config.epochs,
                              batch_idx, train_batch_num,
                              loss.item()))

                # use tensorboard
                if self.tensorboard:
                    current_global_step = self.ckpt.step()
                    self.summary_writer.add_scalar('train/loss',
                                                   loss, current_global_step)
                    self.summary_writer.add_images("train/input_img",
                                                   batch_input,
                                                   current_global_step)
                    self.summary_writer.add_images("train/mean_img",
                                                   batch_results['mean'],
                                                   current_global_step)

            # save model
            self.save(self.ckpt, epoch)
            self.model.train()

            # use tensorboard
            if self.tensorboard:
                print(self.optimizer.get_lr(), epoch)
                self.summary_writer.add_scalar('epoch_lr',
                                               self.optimizer.get_lr(), epoch)

            # test model
            self.test(data_loader)


        self.summary_writer.close()

    def test(self, data_loader):
        with torch.no_grad():
            if self.uncertainty=='aleatoric' or self.uncertainty=='normal':
                self.model.eval()

            total_psnr = 0.
            psnrs = []
            test_batch_num = len(data_loader['test'])
            for batch_idx, batch_data in enumerate(data_loader['test']):
                batch_input, batch_label = batch_data

                # forward
                batch_results = self.model(batch_input, )
                current_psnr = calc_psnr(batch_results['mean'], batch_input)
                psnrs.append(current_psnr)
                total_psnr = sum(psnrs) / len(psnrs)
                print("Test iter: {:03d}/{:03d}, Total: {:5f}, Current: {:05f}".format(
                    batch_idx, test_batch_num,
                    total_psnr, psnrs[batch_idx]))

            # use tensorboard
            if self.tensorboard:
                self.summary_writer.add_scalar('test/psnr',
                                               total_psnr, self.ckpt.last_epoch)
                self.summary_writer.add_images("test/input_img",
                                               batch_input, self.ckpt.last_epoch)
                self.summary_writer.add_images("test/mean_img",
                                               batch_results['mean'], self.ckpt.last_epoch)
                if not self.uncertainty=='normal':
                    self.summary_writer.add_images("test/var_img",
                                                   torch.sigmoid(batch_results['var']),
                                                   self.ckpt.last_epoch)

    def load(self, ckpt):
        ckpt.load() # load ckpt
        self.model.load(ckpt) # load model
        self.optimizer.load(ckpt) # load optimizer


    def save(self, ckpt, epoch):
        ckpt.save(epoch) # save ckpt: global_step, last_epoch
        self.model.save(ckpt, epoch) # save model: weight
        self.optimizer.save(ckpt) # save optimizer:


