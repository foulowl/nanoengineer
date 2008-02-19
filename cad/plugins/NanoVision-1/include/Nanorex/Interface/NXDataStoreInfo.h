// Copyright 2008 Nanorex, Inc.  See LICENSE file for details.

#ifndef NX_DATASTOREINFO_H
#define NX_DATASTOREINFO_H

#include <map>
#include <vector>
#include <string>
using namespace std;

#include "Nanorex/Utility/NXProperties.h"

namespace Nanorex {


/* CLASS: NXDataStoreInfo */
/**
 * Fill this out.
 *
 * @ingroup NanorexInterface PluginArchitecture
 */
class NXDataStoreInfo {
	public:
		NXDataStoreInfo();
		
		//
		// Single structures
		//
		bool isSingleStructure();
		void setIsSingleStructure(bool _isSingleStructure);
		
		const string& getSingleStructureFileName();
		int getSingleStructureId();
		
		//
		// Simulation results
		//
		bool isSimulationResults();
		void setIsSimulationResults(bool _isSimulationResults);
		
		NXProperties* getInputParameters();
		void setInputParameters(NXProperties* parameters);
		
		vector<string> getInputFileNames();
		void addInputStructure(const string& fileName);
		int getInputStructureId(const string& fileName);
		
		NXProperties* getResultsSummary();
		void setResultsSummary(NXProperties* resultsSummary);
		
		vector<string> getTrajectoryNames();
		void addTrajectory(const string& name, int frameSetId);
		int getTrajectoryId(const string& name);
		
		void setLastFrame(int frameSetId, bool isLastFrame);
		bool isLastFrame(int frameSetId);
		
		bool storeIsComplete(int frameSetId);
		void setStoreComplete(int frameSetId, bool storeIsComplete);
		
		
		//
		// General
		//
		// Data store file names
		const string& getFileName(int frameSetId);
		void setFileName(const string& fileName, int frameSetId);

		// Data store file handles
		void setHandle(int frameSetId, void* handle);
		void* getHandle(int frameSetId);
		
	private:
		bool _isSimulationResults, _isSingleStructure;
		NXProperties* _inputParameters, *_resultsSummary;
	
		// Maps frame set id to its source file name.
		map<int, string> _fileNames;
		
		// Maps input structure name to its frame set id.
		map<string, int> _inputStructures;
		
		// Maps trajectory name to its frame set id.
		map<string, int> _trajectories;
		
		// Maps frame set id to its file handle.
		map<int, void*> _handle;
		
		// Maps frame set id to its last-frame status
		map<int, bool> _isLastFrame;
		
		// Maps frame set id to its store-complete status
		map<int, bool> _storeIsComplete;
};


} // Nanorex::

#endif
