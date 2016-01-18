import numpy as np
from random import sample
from scipy.sparse import csgraph
import datetime
import os.path
import matplotlib.pyplot as plt
# local address to save simulated users, simulated articles, and results
from conf import sim_files_folder, save_address
from util_functions import featureUniform
from Articles import ArticleManager
from Users import UserManager
from LinUCB import *
from GOBLin import *
from CoLin import *
from W_W0Alg import W_W0_Algorithm
from W_Alg import WAlgorithm, WknowThetaAlgorithm
import argparse

class simulateOnlineData(object):
	def __init__(self, dimension, iterations, articles, users, 
					batchSize = 1000,
					noise = lambda : 0,
					matrixNoise = lambda:0,
					type_ = 'UniformTheta', 
					signature = '', 
					poolArticleSize = 10, 
					sparseLevel = 0,  
					epsilon = 1, Gepsilon = 1, noiseLevel =0, matrixNoiseLevel=0):

		self.simulation_signature = signature
		self.type = type_

		self.dimension = dimension
		self.iterations = iterations
		self.noise = noise
		self.matrixNoise = matrixNoise # noise to be added to W
		self.noiseLevel = noiseLevel
		self.matrixNoiseLevel = matrixNoiseLevel
		
		self.articles = articles 
		self.users = users
		self.sparseLevel = sparseLevel

		self.poolArticleSize = poolArticleSize
		self.batchSize = batchSize
		
		#self.W = self.initializeW(epsilon)
		#self.GW = self.initializeGW(Gepsilon)
		
		self.W, self.W0 = self.constructAdjMatrix(sparseLevel)
		W = self.W.copy()
		self.GW = self.constructLaplacianMatrix(W, Gepsilon)
		
	def constructGraph(self):
		n = len(self.users)	

		G = np.zeros(shape = (n, n))
		for ui in self.users:
			for uj in self.users:
				G[ui.id][uj.id] = np.dot(ui.theta, uj.theta) # is dot product sufficient
		return G
		
	def constructAdjMatrix(self, m):
		n = len(self.users)	

		G = self.constructGraph()
		W = np.zeros(shape = (n, n))
		W0 = np.zeros(shape = (n, n)) # corrupt version of W
		for ui in self.users:
			for uj in self.users:
				W[ui.id][uj.id] = G[ui.id][uj.id]
				sim = W[ui.id][uj.id] + self.matrixNoise() # corrupt W with noise
				if sim < 0:
					sim = 0
				W0[ui.id][uj.id] = sim
				
			# find out the top M similar users in G
			if m>0 and m<n:
				similarity = sorted(G[ui.id], reverse=True)
				threshold = similarity[m]				
				
				# trim the graph
				for i in range(n):
					if G[ui.id][i] <= threshold:
						W[ui.id][i] = 0;
						W0[ui.id][i] = 0;
					
			W[ui.id] /= sum(W[ui.id])
			W0[ui.id] /= sum(W0[ui.id])
		#W = np.identity(n)   #If W is identity, CoLin goes back to LinUCB
		return [W, W0]

	def constructLaplacianMatrix(self, G, Gepsilon):
		print G
		#Convert adjacency matrix of weighted graph to adjacency matrix of unweighted graph
		for i in self.users:
			for j in self.users:
				if G[i.id][j.id] > 0:
					G[i.id][j.id] = 1	

		L = csgraph.laplacian(G, normed = False)
		I = np.identity(n = G.shape[0])
		GW = I+ Gepsilon*L  # W is a double stochastic matrix
		print 'GW', GW
		return GW.T

	def getW(self):
		return self.W
	def getW0(self):
		return self.W0
	def getFullW(self):

		return self.FullW
	
	def getGW(self):
		print 'GW', self.GW
		return self.GW

	def getTheta(self):
		Theta = np.zeros(shape = (self.dimension, len(self.users)))
		for i in range(len(self.users)):
			Theta.T[i] = self.users[i].theta
		return Theta

	def CoTheta(self):
		for ui in self.users:
			ui.CoTheta = np.zeros(self.dimension)
			for uj in self.users:
				ui.CoTheta += self.W[uj.id][ui.id] * np.asarray(uj.theta)
			print 'Users', ui.id, 'CoTheta', ui.CoTheta	
	
	def batchRecord(self, iter_):
		print "Iteration %d"%iter_, "Pool", len(self.articlePool)," Elapsed time", datetime.datetime.now() - self.startTime

	def regulateArticlePool(self):
		# Randomly generate articles
		self.articlePool = sample(self.articles, self.poolArticleSize)   

	def getReward(self, user, pickedArticle):
		return np.dot(user.CoTheta, pickedArticle.featureVector)

	def GetOptimalReward(self, user, articlePool):		
		maxReward = float('-inf')
		for x in articlePool:	 
			reward = self.getReward(user, x)
			if reward > maxReward:
				maxReward = reward
		return maxReward
	
	def getL2Diff(self, x, y):
		return np.linalg.norm(x-y) # L2 norm

	def runAlgorithms(self, algorithms):
		self.startTime = datetime.datetime.now()
		timeRun = self.startTime.strftime('_%m_%d') 
		filenameWriteRegret = os.path.join(save_address, 'AccRegret' + timeRun + '.csv')
		filenameWritePara = os.path.join(save_address, 'ParameterEstimation' + timeRun + '.csv')
		for alg_name, alg in algorithms.items():
			fileSig = str(alg_name) + '_UserNum'+ str(len(self.users)) + '_Sparsity' + str(self.sparseLevel) +'_Noise'+str(self.noiseLevel)+ '_matrixNoise'+str(self.matrixNoiseLevel)
		filenameWriteResult = os.path.join(save_address, fileSig + timeRun + '.csv')

		# compute co-theta for every user
		self.CoTheta()

		tim_ = []
		BatchCumlateRegret = {}
		AlgRegret = {}
		ThetaDiffList = {}
		CoThetaDiffList = {}
		WDiffList = {}
		
		ThetaDiff = {}
		CoThetaDiff = {}
		WDiff = {}
		
		# Initialization
		userSize = len(self.users)
		for alg_name, alg in algorithms.items():
			AlgRegret[alg_name] = []
			BatchCumlateRegret[alg_name] = []
			if alg.CanEstimateUserPreference:
				ThetaDiffList[alg_name] = []
			if alg.CanEstimateCoUserPreference:
				CoThetaDiffList[alg_name] = []
			if alg.CanEstimateW:
				WDiffList[alg_name] = []
		'''
		with open(filenameWriteRegret, 'w') as f:
			f.write('Time(Iteration)')
			f.write(',' + ','.join( [str(alg_name) for alg_name in algorithms.iterkeys()]))
			f.write('\n')
		with open(filenameWritePara, 'w') as f:
			f.write('Time(Iteration)')
			f.write(',' + ','.join([str(alg_name)+'CoTheta' for alg_name in algorithms.iterkeys()]))
			f.write(','+ ','.join([str(alg_name)+'Theta' for alg_name in ThetaDiffList.iterkeys()]))
			f.write(','+ ','.join([str(alg_name)+'W' for alg_name in WDiffList.iterkeys()]))
			f.write('\n')
		'''
		
		# Loop begin
		for iter_ in range(self.iterations):
			# prepare to record theta estimation error
			for alg_name, alg in algorithms.items():
				if alg.CanEstimateUserPreference:
					ThetaDiff[alg_name] = 0
				if alg.CanEstimateCoUserPreference:
					CoThetaDiff[alg_name] = 0
				if alg.CanEstimateW:
					WDiff[alg_name] = 0
					
			for u in self.users:
				self.regulateArticlePool() # select random articles

				noise = self.noise()
				#get optimal reward for user x at time t
				OptimalReward = self.GetOptimalReward(u, self.articlePool) + noise
							
				for alg_name, alg in algorithms.items():
					pickedArticle = alg.decide(self.articlePool, u.id)
					reward = self.getReward(u, pickedArticle) + noise
					alg.updateParameters(pickedArticle, reward, u.id)

					regret = OptimalReward - reward	
					AlgRegret[alg_name].append(regret)

					#update parameter estimation record
					if alg.CanEstimateUserPreference:
						ThetaDiff[alg_name] += self.getL2Diff(u.theta, alg.getTheta(u.id))
					if alg.CanEstimateCoUserPreference:
						CoThetaDiff[alg_name] += self.getL2Diff(u.CoTheta, alg.getCoTheta(u.id))
					if alg.CanEstimateW:
						WDiff[alg_name] += self.getL2Diff(self.W.T[u.id], alg.getW(u.id))	
			
			if 'syncCoLinUCB' in algorithms:
				algorithms['syncCoLinUCB'].LateUpdate()	

			for alg_name, alg in algorithms.items():
				if alg.CanEstimateUserPreference:
					ThetaDiffList[alg_name] += [ThetaDiff[alg_name]/userSize]
				if alg.CanEstimateCoUserPreference:
					CoThetaDiffList[alg_name] += [CoThetaDiff[alg_name]/userSize]
				if alg.CanEstimateW:
					WDiffList[alg_name] += [WDiff[alg_name]/userSize]	
				
			if iter_%self.batchSize == 0:
				self.batchRecord(iter_)
				tim_.append(iter_)
				for alg_name in algorithms.iterkeys():
					BatchCumlateRegret[alg_name].append(sum(AlgRegret[alg_name]))
				'''
				with open(filenameWriteRegret, 'a+') as f:
					f.write(str(iter_))
					f.write(',' + ','.join([str(BatchCumlateRegret[alg_name][-1]) for alg_name in algorithms.iterkeys()]))
					f.write('\n')
				with open(filenameWritePara, 'a+') as f:
					f.write(str(iter_))
					f.write(',' + ','.join([str(CoThetaDiffList[alg_name][-1]) for alg_name in algorithms.iterkeys()]))
					f.write(','+ ','.join([str(ThetaDiffList[alg_name][-1]) for alg_name in ThetaDiffList.iterkeys()]))
					f.write(','+ ','.join([str(ThetaDiffList[alg_name][-1]) for alg_name in WDiffList.iterkeys()]))
					f.write('\n')
				'''
					
		# plot the results	
		f, axa = plt.subplots(2, sharex=True)
		for alg_name in algorithms.iterkeys():	
			axa[0].plot(tim_, BatchCumlateRegret[alg_name],label = alg_name)
			print '%s: %.2f' % (alg_name, BatchCumlateRegret[alg_name][-1])
			'''
			with open(filenameWriteResult, 'a+') as f:
				f.write(str(alg_name)+ ','+ str( BatchCumlateRegret[alg_name][-1]))
				f.write('\n')
			'''
		
		axa[0].legend(loc='lower right',prop={'size':9})
		axa[0].set_xlabel("Iteration")
		axa[0].set_ylabel("Regret")
		axa[0].set_title("Accumulated Regret")
		
		# plot the estimation error of co-theta
		time = range(self.iterations)
		for alg_name, alg in algorithms.items():
			if alg.CanEstimateUserPreference:
				axa[1].plot(time, ThetaDiffList[alg_name], label = alg_name + '_Theta')
			if alg.CanEstimateCoUserPreference:
				axa[1].plot(time, CoThetaDiffList[alg_name], label = alg_name + '_CoTheta')
		
		axa[1].legend(loc='upper right',prop={'size':6})
		axa[1].set_xlabel("Iteration")
		axa[1].set_ylabel("L2 Diff")
		axa[1].set_yscale('log')
		axa[1].set_title("Parameter estimation error")
		plt.show()
		
if __name__ == '__main__':

	iterations = 300
	NoiseScale = .01

	dimension = 5
	alpha  = 0.1
	lambda_ = 0.2   # Initialize A
	epsilon = 0.3 # initialize W
	eta_ = 0.1
	alphaConstant = .01

	n_articles = 1000
	ArticleGroups = 5

	n_users = 100
	UserGroups = 5	
	

	poolSize = 10
	batchSize = 10

	# Matrix parameters
	matrixNoise = 0.01
	sparseLevel = 100  # if smaller or equal to 0 or larger or enqual to usernum, matrix is fully connected


	# Parameters for GOBLin
	G_alpha = alpha
	G_lambda_ = lambda_
	Gepsilon = epsilon


	parser = argparse.ArgumentParser(description = '')
	parser.add_argument('--alg', dest='alg', help='Select a specific algorithm, could be CoLin, GOBLin, AsyncCoLin, or SyncCoLin')

	parser.add_argument('--showheatmap', action='store_true',
	                help='Show heatmap of relation matrix.') 
	parser.add_argument('--userNum', dest = 'userNum', help = 'Set the userNum, can be 40, 80, 100')
	parser.add_argument('--Sparsity', dest = 'SparsityLevel', help ='Set the SparsityLevel by choosing the top M most connected users, should be smaller than userNum, when equal to userNum, we are using a full connected graph')
	parser.add_argument('--NoiseScale', dest = 'NoiseScale', help = 'Set NoiseScale')
	parser.add_argument('--matrixNoise', dest = 'matrixNoise', help = 'Set MatrixNoiseScale')
	args = parser.parse_args()

	algName = str(args.alg)
	n_users = int(args.userNum)
	sparseLevel = int(args.SparsityLevel)
	NoiseScale = float(args.NoiseScale)
	matrixNoise = float(args.matrixNoise)

	
	userFilename = os.path.join(sim_files_folder, "users_"+str(n_users)+"+dim-"+str(dimension)+ "Ugroups" + str(UserGroups)+".json")
	
	#"Run if there is no such file with these settings; if file already exist then comment out the below funciton"
	# we can choose to simulate users every time we run the program or simulate users once, save it to 'sim_files_folder', and keep using it.
	UM = UserManager(dimension, n_users, UserGroups = UserGroups, thetaFunc=featureUniform, argv={'l2_limit':1})
	#users = UM.simulateThetafromUsers()
	#UM.saveUsers(users, userFilename, force = False)
	users = UM.loadUsers(userFilename)

	articlesFilename = os.path.join(sim_files_folder, "articles_"+str(n_articles)+"+dim"+str(dimension) + "Agroups" + str(ArticleGroups)+".json")
	# Similarly, we can choose to simulate articles every time we run the program or simulate articles once, save it to 'sim_files_folder', and keep using it.
	AM = ArticleManager(dimension, n_articles=n_articles, ArticleGroups = ArticleGroups,
			FeatureFunc=featureUniform,  argv={'l2_limit':1})
	#articles = AM.simulateArticlePool()
	#AM.saveArticles(articles, articlesFilename, force=False)
	articles = AM.loadArticles(articlesFilename)

	simExperiment = simulateOnlineData(dimension  = dimension,
						iterations = iterations,
						articles=articles,
						users = users,		
						noise = lambda : np.random.normal(scale = NoiseScale),
						matrixNoise = lambda : np.random.normal(scale = matrixNoise),
						batchSize = batchSize,
						type_ = "UniformTheta", 
						signature = AM.signature,
						sparseLevel = sparseLevel,
						poolArticleSize = poolSize,  epsilon = epsilon, Gepsilon =Gepsilon, noiseLevel= NoiseScale, matrixNoiseLevel=matrixNoise)

	print "Starting for ", simExperiment.simulation_signature

	#for i in range(10):
	algorithms = {}
	
	if algName == 'LinUCB':
		algorithms['LinUCB'] = N_LinUCBAlgorithm(dimension = dimension, alpha = alpha, lambda_ = lambda_, n = n_users)
	if algName == 'GOBLin':
		algorithms['GOBLin'] = GOBLinAlgorithm( dimension= dimension, alpha = alphaConstant, lambda_ = G_lambda_, n = n_users, W = simExperiment.getGW() )
	if algName =='SyncCoLin':
		algorithms['syncCoLinUCB'] = syncCoLinUCBAlgorithm(dimension=dimension, alpha = alphaConstant, lambda_ = lambda_, n = n_users, W = simExperiment.getW())
	if algName == 'AsyncCoLin':
		algorithms['AsyncCoLinUCB'] = AsyCoLinUCBAlgorithm(dimension=dimension, alpha = alphaConstant, lambda_ = lambda_, n = n_users, W = simExperiment.getW())
	if algName =='ALL':
		algorithms['LinUCB'] = N_LinUCBAlgorithm(dimension = dimension, alpha = alpha, lambda_ = lambda_, n = n_users)
		algorithms['GOBLin'] = GOBLinAlgorithm( dimension= dimension, alpha = alphaConstant, lambda_ = G_lambda_, n = n_users, W = simExperiment.getGW() )
		algorithms['syncCoLinUCB'] = syncCoLinUCBAlgorithm(dimension=dimension, alpha = alphaConstant, lambda_ = lambda_, n = n_users, W = simExperiment.getW())
		algorithms['AsyncCoLinUCB'] = AsyCoLinUCBAlgorithm(dimension=dimension, alpha = alphaConstant, lambda_ = lambda_, n = n_users, W = simExperiment.getW())
		

	#algorithms['UniformLinUCB'] = Uniform_LinUCBAlgorithm(dimension = dimension, alpha = alpha, lambda_ = lambda_)
	#algorithms['WCoLinUCB'] =  WAlgorithm(dimension = dimension, alpha = alpha, lambda_ = lambda_, eta_ = eta_, n = n_users)
	#algorithms['WknowTheta'] = WknowThetaAlgorithm(dimension = dimension, alpha = alpha, lambda_ = lambda_, eta_ = eta_, n = n_users, theta = simExperiment.getTheta())
	#algorithms['W_W0'] = W_W0_Algorithm(dimension = dimension, alpha = alpha, lambda_ = lambda_, eta_ = eta_, n = n_users, W0 = simExperiment.getW0())

	#algorithms['eGreedy'] = eGreedyAlgorithm(epsilon = eGreedy)
	#algorithms['UCB1'] = UCB1Algorithm()
	
	simExperiment.runAlgorithms(algorithms)